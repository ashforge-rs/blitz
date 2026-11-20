# blitz

FastAPI boilerplate. Clone, configure, extend.

## Quick start

```bash
cp .env.example .env
make install
make dev          # http://localhost:8000
```

## Commands

| Command        | Description                                                |
| -------------- | ---------------------------------------------------------- |
| `make install` | Install all dependencies via `uv sync`                     |
| `make help`    | List every target                                          |
| `make dev`     | Start dev server with hot-reload (`SERVICE=api`, `PORT=8000`) |
| `make domain DOMAIN=orders` | Scaffold a domain + tests and register it     |
| `make lint`    | Run Ruff linter                                            |
| `make fmt`     | Auto-format with Ruff                                      |
| `make check`   | Format, lint, then mypy type-check                         |
| `make test`    | Run pytest                                                 |
| `make test-unit` / `test-integration` / `test-fuzz` | Run one test tier      |
| `make coverage` | pytest with coverage report (fails under 80 %)           |
| `make openapi` | Generate the OpenAPI schema (`scripts/generate_openapi.py`) |
| `make docker-build SERVICE=api` | Build a service image locally         |
| `make docker-run SERVICE=api`   | Run a locally built service image     |
| `make clean`   | Remove caches and build artifacts                          |

**Python:** 3.15+ (`requires-python = ">=3.15"`; Docker images use `python:3.15-slim`).

**Tools:** `uv` (package management), `ruff` (lint + format), `mypy` (strict type-check) and `pytest` — no other tooling. `uv run mypy src/` must stay clean; CI enforces it.

## Project structure

```
src/
├── app.py              # create_app() factory — main entry point for customisation
├── config.py           # Settings (pydantic-settings, loads .env)
├── context.py          # RequestContext dataclass + ContextVar helpers
├── lifespan.py         # Startup / graceful-shutdown lifecycle (domain bootstrap + aclose)
├── bootstrap.py        # Domain-module contract: BootstrapContext + validation
├── deps.py             # Shared FastAPI deps: RequestContextDep, SettingsDep, Audit*Dep
├── routing.py          # ResultRouter — unwraps Result[T, DomainError] return values
├── service.py          # Base Service class — extend for every domain service
├── state.py            # get_domain(): typed lookup of bootstrapped domains
├── store/
│   ├── protocol.py     # KeyValueStore[K,V] Protocol (Dependency Inversion)
│   └── memory.py       # InMemoryStore — default, test-friendly implementation
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
│   ├── helpers.py      # Convenience helpers for emitting audit events
│   ├── integrity.py    # AuditIntegrity — tamper-evidence (sequence + checksum)
│   └── backends/
│       ├── loguru.py   # Default: structured JSON via Loguru
│       ├── noop.py     # Silent discard
│       ├── multi.py    # Fan-out to multiple backends simultaneously
│       └── stream.py   # Async-generator streaming backend
├── errors/
│   ├── exceptions.py   # AppError hierarchy (NotFoundError, ConflictError, …) to raise
│   ├── domain.py       # DomainError (typed Failure values) + DomainFailure
│   ├── problem.py      # RFC 9457 Problem Details builder (problem_response)
│   └── handlers.py     # Global exception handlers + error sanitisation
├── log/
│   └── setup.py        # Loguru configuration (JSON in prod, pretty in dev)
├── metrics/
│   └── registry.py     # Custom prometheus_client helpers
├── telemetry/
│   └── setup.py        # OpenTelemetry tracing initialisation
├── routes/
│   ├── health.py       # GET /live  GET /health
│   └── metrics.py      # GET /metrics
├── domains/            # Bounded-context business logic (one sub-package per domain)
│   └── example/        # ← reference domain (rename or delete)
│       ├── models.py       # Pydantic models
│       ├── errors.py       # Typed domain errors (error codes, not strings)
│       ├── repository.py   # Data-access layer (depends on KeyValueStore protocol)
│       ├── service.py      # Business logic (depends on repository)
│       ├── domain.py       # bootstrap() + make_router() + Domain container
│       └── dependencies.py # FastAPI Annotated dependency aliases
└── services/           # Independent ASGI application instances
    └── api/            # Default service — wires domains into the FastAPI app
        ├── domains.py      # DOMAINS — modules this service serves
        ├── main.py         # create_app() call + uvicorn entry point
        └── Dockerfile      # Per-service container image
```

## Four-layer domain pattern

Every domain follows a strict four-layer stack (each layer depends only on the layer below it):

```
KeyValueStore (protocol)
    └─▶ Repository  (data-access)
            └─▶ Service     (business logic, returns Result[T, DomainError])
                    └─▶ Domain      (HTTP routing + bootstrap)
```

Domains live under `src/domains/<name>/` and are registered with a service in
`src/services/<service>/domains.py`.

### 1 — Scaffold a domain

```bash
make domain DOMAIN=orders                 # entity defaults to the singular: Order
make domain DOMAIN=people ENTITY=Person   # override the entity name
```

`scripts/new_domain.py` generates the package below plus unit / integration / fuzz tests
under `tests/domains/orders/`, and appends the module to `src/services/api/domains.py`.
The test suite's `client` fixture serves every registered domain, so the generated tests
run straight away. `src/domains/example/` is the fuller reference (tracing, audit metadata).

```
src/domains/orders/
├── models.py        # Order, CreateOrderRequest, UpdateOrderRequest
├── errors.py        # OrderErrorCode + OrderError(DomainError) with code → HTTP status
├── repository.py    # OrderRepository(store: KeyValueStore[str, Order])
├── service.py       # OrderService — every method returns Result[T, OrderError]
├── dependencies.py  # OrderServiceDep (resolves the bootstrapped service)
└── domain.py        # OrdersDomain container, ResultRouter routes, make_router(), bootstrap()
```

### 2 — The domain contract

`create_app(domains=[...])` validates each module when the app is created
(see `src/bootstrap.py`). A module exposes any of:

| Hook | When | Purpose |
| --- | --- | --- |
| `make_router() -> APIRouter` | app creation | Routes, mounted under `API_PREFIX` |
| `async bootstrap(boot: BootstrapContext) -> Domain` | lifespan startup | Open pools/clients, wire layers, return the domain instance |
| `register_exception_handlers(app)` | app creation | Optional custom handlers |

`BootstrapContext` carries `settings`, `audit_backend`, `audit_integrity` and `extra`
(the `extra_context` dict). If the returned instance has `async aclose()`, it is awaited on
shutdown after in-flight requests drain, in reverse bootstrap order. It also runs when a
later domain's bootstrap fails, so a failed startup never leaks connections. Each domain
must return a distinct type; resolve it with `state.get_domain(request, OrdersDomain)`.

```python
# src/domains/orders/errors.py
@dataclass(frozen=True, slots=True)
class OrderError(DomainError[OrderErrorCode]):
    order_id: str | None = None

    STATUS: ClassVar[Mapping[str, int]] = {
        OrderErrorCode.NOT_FOUND: 404,
        OrderErrorCode.STORAGE_ERROR: 500,  # 5xx: client sees only the reason phrase
    }
```

```python
# src/domains/orders/domain.py
_router = ResultRouter(prefix="/orders", tags=["orders"])


@_router.get("/{order_id}")
async def get_order(
    order_id: str, svc: OrderServiceDep, ctx: RequestContextDep
) -> Result[Order, OrderError]:
    return await svc.get(order_id, ctx)


async def bootstrap(boot: BootstrapContext) -> OrdersDomain:
    store: InMemoryStore[str, Order] = InMemoryStore()
    service = OrderService(
        repository=OrderRepository(store=store),
        audit_backend=boot.audit_backend,
        audit_integrity=boot.audit_integrity,
    )
    return OrdersDomain(service=service)
```

`ResultRouter` (`src/routing.py`) unwraps `Success(value)` into the response body and turns
`Failure(OrderError(...))` into a problem response using `OrderError.STATUS`, with the error
code as the `code` member. `response_model` is inferred from `Result[T, ...]`. Shared
dependencies (`RequestContextDep`, `SettingsDep`, `AuditBackendDep`, `AuditIntegrityDep`)
live in `src/deps.py`. For audit events from a service, use
`audit.helpers.log_operation(backend, integrity, ctx, "orders.create", resource_id=...)`.

Domain routers are mounted under `API_PREFIX` (default `/v1`), so the router above serves
`/v1/orders/{order_id}`. Built-in routes (`/live`, `/health`, `/metrics`, `/docs`) are never prefixed.

## Key extension points

### Error responses (RFC 9457)

Every error — exception handlers and middleware alike — is `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Order '42' not found",
  "instance": "/v1/orders/42",
  "request_id": "0f8fad5b..."
}
```

Return `Failure(DomainError)` from a `ResultRouter` route (the domain pattern above), or raise
`AppError` subclasses (`NotFoundError`, `ConflictError`, …) or `HTTPException`, and the
global handlers do the rest. For a custom domain error handler, return
`errors.problem.problem_response(status, detail, request=request, code=...)` — extra keyword
arguments become extension members. Validation errors carry the field list in `errors`.

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

The rate limiter uses the **async** `limits.aio` API and accepts any
[`limits.aio.storage.Storage`](https://limits.readthedocs.io/en/stable/async.html) implementation,
so network-backed storages never block the event loop.
Default is `MemoryStorage` (single-process). Pass a different backend to share state across workers:

```python
from limits.aio.storage import MemoryStorage  # built-in default
# from limits.aio.storage import RedisStorage  # uv add "limits[async-redis]"
# RedisStorage("async+redis://localhost:6379")

app = create_app(rate_limit_storage=MemoryStorage())
```

If the storage backend errors, requests are allowed through (fail-open) and a warning is logged.
`Retry-After` on a `429` is the number of seconds until the window frees a slot.

### Custom metrics

```python
from metrics.registry import counter

orders_total = counter("orders_total", "Total orders processed", ["status"])
orders_total.labels(status="completed").inc()
```

### Extra context properties

Pass a dict to `extra_context`; each key is set on `app.state`, and the dict is handed to every
domain's `bootstrap()` as `boot.extra`:

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
    ctx.request_id  # X-Request-ID header or UUID4
    ctx.set("key", value)
    ctx.get("key")
```

## Environment variables

See `.env.example` for all options. Key variables:

| Variable                   | Default       | Description                           |
| -------------------------- | ------------- | ------------------------------------- |
| `ENVIRONMENT`              | `development` | `development` / `production` / `test` |
| `LOG_LEVEL`                | `INFO`        | Loguru log level                      |
| `WORKERS`                  | `1`           | Uvicorn worker processes              |
| `HOST` / `PORT`            | `127.0.0.1` / `8000` | Bind address for `python -m services.api.main` |
| `MAX_REQUEST_SIZE_BYTES`   | `10485760`    | 10 MB body limit                      |
| `REQUEST_TIMEOUT_SECONDS`  | `30.0`        | Per-request timeout                   |
| `RATE_LIMIT`               | `100/minute`  | Rate limit per IP                     |
| `METRICS_ENDPOINT_ENABLED` | `true`        | Expose `/metrics`                     |
| `METRICS_REQUIRE_AUTH`     | `false`       | Gate `/metrics` behind auth           |
| `SHUTDOWN_TIMEOUT_SECONDS` | `30.0`        | Drain timeout on SIGTERM              |
| `API_PREFIX`               | `/v1`         | Prefix for domain routes (`""` = none) |
| `OTEL_HEADERS`             | `""`          | OTLP auth headers `k=v,k2=v2` (secret) |

List settings (`ALLOWED_ORIGINS`, `TRUSTED_PROXIES`, `ALLOWED_HOSTS`, `OPENAPI_SERVERS`) accept
comma-separated (`a,b`) or JSON (`["a","b"]`) values.

## Built-in endpoints

| Endpoint       | Description                                              |
| -------------- | -------------------------------------------------------- |
| `GET /live`    | Liveness probe — always `200 {"status":"ok"}`            |
| `GET /health`  | Readiness probe — `200`/`503` based on registered checks |
| `GET /metrics` | Prometheus exposition format                             |
| `GET /docs`    | Swagger UI (disabled in production)                      |

## Conventions

- All source code lives under `src/`; each domain gets its own sub-package
- `PYTHONPATH` is `src/` — import modules directly: `from config import Settings`
- Settings are read once and cached; override via env vars or by passing `Settings()` to `create_app()`
- Secret settings are typed `SecretStr` (masked in repr/logs/dumps); unwrap with `.get_secret_value()` only where used
- In `production` environment: Loguru emits JSON, `/docs` is disabled, unhandled exceptions return sanitised `500` responses
- Middleware execution order (outermost → innermost): TrustedHost → CORS → InFlight → Audit → SecurityHeaders → Timeout → SizeLimit → RateLimit → Context → Handler
- Every `Settings` field must appear in `.env.example` (a test enforces it)
- Tests: `client` serves every registered domain; for a custom app use the `make_app(settings={...}, **create_app_kwargs)`
  and `async with make_client(app) as c:` fixtures (lifespan runs, a local `.env` is never read)
