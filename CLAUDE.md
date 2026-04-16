# blitz

Production-grade FastAPI boilerplate. Clone, configure, extend.

## Quick start

```bash
cp .env.example .env
make install
make dev          # http://localhost:8000
```

## Commands

| Command        | Description                          |
|----------------|--------------------------------------|
| `make install` | Install all dependencies via `uv sync` |
| `make dev`     | Start dev server with hot-reload     |
| `make lint`    | Run Ruff linter                      |
| `make fmt`     | Auto-format with Ruff                |
| `make check`   | Format then lint                     |
| `make test`    | Run pytest                           |
| `make clean`   | Remove caches and build artifacts    |

**Tools:** `uv` (package management) and `ruff` (lint + format) — no other tooling.

## Project structure

```
src/
├── app.py              # create_app() factory — main entry point for customisation
├── main.py             # Uvicorn entry point; exports module-level `app`
├── config.py           # Settings (pydantic-settings, loads .env)
├── context.py          # RequestContext dataclass + ContextVar helpers
├── lifespan.py         # Startup / graceful-shutdown lifecycle
├── service.py          # Base Service class — extend for every domain service
├── auth/
│   ├── protocol.py     # AuthProvider Protocol (implement to add auth)
│   └── dependency.py   # FastAPI dependency: get_auth_context()
├── middleware/
│   ├── stack.py        # Registers all middleware in correct order
│   ├── audit.py        # Per-request audit event dispatch
│   ├── context.py      # Injects RequestContext into request.state.ctx
│   ├── rate_limit.py   # Moving-window rate limiting (pluggable storage)
│   ├── security.py     # Security response headers
│   ├── size_limit.py   # Request body size guard (413)
│   └── timeout.py      # Per-request timeout (504)
├── audit/
│   ├── backend.py      # AuditBackend ABC + AuditEvent dataclass
│   └── backends/
│       ├── loguru.py   # Default: structured JSON via Loguru
│       └── noop.py     # Silent discard
├── errors/
│   └── handlers.py     # Global exception handlers + error sanitisation
├── log/
│   └── setup.py        # Loguru configuration (JSON in prod, pretty in dev)
├── metrics/
│   └── registry.py     # Custom prometheus_client helpers
├── routes/
│   ├── health.py       # GET /live  GET /health
│   └── metrics.py      # GET /metrics
└── example/            # ← example domain (delete or rename)
    └── domain.py       # bootstrap() + make_router() + ExampleService
```

## Service-oriented pattern

Each feature lives in its own package under `src/`. The package exposes three
things in `domain.py`:

| Name | Kind | Purpose |
|---|---|---|
| `XService(Service)` | class | Business logic; declare deps in `__init__` |
| `make_router() -> APIRouter` | function | Returns the router; called at app-creation time |
| `bootstrap(settings, **kwargs)` | async function | Initialises clients/pools; called once at startup |

### 1 — Create a domain

```
src/orders/
├── __init__.py
└── domain.py
```

```python
# src/orders/domain.py
from __future__ import annotations
from fastapi import APIRouter, Request
from service import Service
from config import Settings


class OrderService(Service):
    def __init__(self, db: Any, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def find_by_id(self, order_id: str) -> dict | None:
        raise NotImplementedError


class OrdersDomain:
    def __init__(self, service: OrderService) -> None:
        self.service = service


_router = APIRouter(prefix="/orders", tags=["orders"])

@_router.get("/{order_id}")
async def get_order(order_id: str, request: Request) -> dict:
    domain: OrdersDomain = request.app.state.domains["orders.domain"]
    result = await domain.service.find_by_id(order_id)
    return result or {}


def make_router() -> APIRouter:
    return _router


async def bootstrap(settings: Settings, **kwargs) -> OrdersDomain:
    db = ...  # create your DB pool here
    service = OrderService(db=db, settings=settings)
    return OrdersDomain(service=service)
```

### 2 — Register with the app

```python
# src/main.py  (or wherever you call create_app)
from orders import domain as orders_domain

app = create_app(domains=[orders_domain])
```

The framework calls `make_router()` at startup to build the OpenAPI schema and
`bootstrap(settings)` during lifespan to initialise connections. The domain
instance is then accessible at `request.app.state.domains["orders.domain"]`.

## Key extension points

### Authentication & authorisation

Implement `AuthProvider` and pass it to `create_app()`:

```python
from auth.protocol import AuthProvider
from context import RequestContext
from starlette.requests import Request

class MyAuthProvider:
    async def authenticate(self, request: Request) -> dict | None:
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        return verify_jwt(token)  # return None to reject

    async def authorize(self, request: Request, principal: dict, ctx: RequestContext) -> bool:
        return "read" in principal.get("scopes", [])

app = create_app(auth_provider=MyAuthProvider())
```

Protect a route with `get_auth_context`:

```python
from fastapi import Depends
from auth.dependency import get_auth_context

@router.get("/secret")
async def secret(principal=Depends(get_auth_context)):
    return {"user": principal}
```

### Audit logging

Implement `AuditBackend` and pass it to `create_app()`:

```python
from audit.backend import AuditBackend, AuditEvent

class DatabaseAuditBackend(AuditBackend):
    async def log(self, event: AuditEvent) -> None:
        await db.audit_logs.insert(event.__dict__)

app = create_app(audit_backend=DatabaseAuditBackend())
```

### Health checks

Pass async callables returning `{"name": str, "healthy": bool, ...}`:

```python
async def check_database() -> dict:
    ok = await db.ping()
    return {"name": "database", "healthy": ok}

app = create_app(health_checks=[check_database])
```

`GET /health` returns `200` when all checks pass, `503` when any fail.

### Rate limit storage

The rate limiter accepts any [`limits.storage.Storage`](https://limits.readthedocs.io/en/stable/storage.html) implementation.
Default is `MemoryStorage` (single-process). Pass a different backend to share state across workers:

```python
from limits.storage import MemoryStorage   # built-in default
# from limits.storage import RedisStorage  # pip install limits[redis]
# from limits.storage import MemcachedStorage

app = create_app(rate_limit_storage=MemoryStorage())
```

### Custom metrics

```python
from metrics.registry import counter

orders_total = counter("orders_total", "Total orders processed", ["status"])
orders_total.labels(status="completed").inc()
```

### Extra context properties

Pass a dict to `extra_context`; each key is set on `app.state`:

```python
app = create_app(extra_context={"db": my_db_pool, "feature_flags": flags})
```

### RequestContext

Every request receives a `RequestContext` accessible via `request.state.ctx`:

```python
from fastapi import Request

@router.get("/")
async def handler(request: Request):
    ctx = request.state.ctx
    ctx.request_id     # X-Request-ID header or UUID4
    ctx.set("key", value)
    ctx.get("key")
```

## Environment variables

See `.env.example` for all options. Key variables:

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `production` / `test` |
| `LOG_LEVEL` | `INFO` | Loguru log level |
| `WORKERS` | `1` | Uvicorn worker processes |
| `MAX_REQUEST_SIZE_BYTES` | `10485760` | 10 MB body limit |
| `REQUEST_TIMEOUT_SECONDS` | `30.0` | Per-request timeout |
| `RATE_LIMIT` | `100/minute` | Rate limit per IP |
| `METRICS_ENDPOINT_ENABLED` | `true` | Expose `/metrics` |
| `METRICS_REQUIRE_AUTH` | `false` | Gate `/metrics` behind auth |
| `SHUTDOWN_TIMEOUT_SECONDS` | `30.0` | Drain timeout on SIGTERM |

## Built-in endpoints

| Endpoint | Description |
|---|---|
| `GET /live` | Liveness probe — always `200 {"status":"ok"}` |
| `GET /health` | Readiness probe — `200`/`503` based on registered checks |
| `GET /metrics` | Prometheus exposition format |
| `GET /docs` | Swagger UI (disabled in production) |

## Conventions

- All source code lives under `src/`; each domain gets its own sub-package
- `PYTHONPATH` is `src/` — import modules directly: `from config import Settings`
- Settings are read once and cached; override via env vars or by passing `Settings()` to `create_app()`
- In `production` environment: Loguru emits JSON, `/docs` is disabled, unhandled exceptions return sanitised `500` responses
- Middleware execution order (outermost → innermost): TrustedHost → CORS → InFlight → Audit → SecurityHeaders → Timeout → SizeLimit → RateLimit → Context → Handler
