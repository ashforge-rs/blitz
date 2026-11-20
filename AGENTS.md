# blitz — agent guide

FastAPI boilerplate: clone, configure, extend. This file is the single source of project rules
for coding agents (Claude Code reads it through `CLAUDE.md`, Copilot through
`.github/agents/blitz-dev.agent.md`). Skills and commands link here instead of restating it.
`src/domains/example/` is the reference implementation; read it when something here is ambiguous.

## Commands

| Command | Use |
| --- | --- |
| `make verify` | **Run before saying work is done.** Format check, lint, mypy, tests; changes nothing |
| `make domain DOMAIN=orders [ENTITY=Order]` | Scaffold a domain + tests and register it |
| `make fmt` / `make lint` | Auto-format / lint with Ruff |
| `make test` · `test-unit` · `test-integration` · `test-fuzz` | All tests / one tier |
| `make coverage` | Tests with coverage (fails under 80 %) |
| `make dev [SERVICE=api] [PORT=8000]` | Hot-reload dev server |
| `make help` | Every target |

Tools are `uv` (never `pip`/`venv`), `ruff`, `mypy --strict` and `pytest`. Python 3.15.
`PYTHONPATH` is `src/`: import `from config import Settings`, never `from src.config ...`.

## Layout

```
src/
├── app.py            # create_app() — the app factory and main customisation point
├── bootstrap.py      # domain-module contract: BootstrapContext, validate_domain_module
├── lifespan.py       # startup (domain bootstrap) / shutdown (drain, aclose)
├── routing.py        # ResultRouter — routes that return Result[T, DomainError]
├── deps.py           # shared deps: RequestContextDep, SettingsDep, AuditBackendDep, AuditIntegrityDep
├── state.py          # get_domain(request, DomainType) — typed lookup of bootstrapped domains
├── config.py         # Settings (pydantic-settings, .env)
├── context.py        # RequestContext (request_id, remote_addr, path, set/get)
├── service.py        # Service base class
├── errors/           # domain.py (DomainError), exceptions.py (AppError), problem.py, handlers.py
├── audit/            # AuditBackend, AuditEvent, integrity, helpers (log_operation, …), backends/
├── auth/             # AuthProvider protocol + get_auth_context dependency
├── middleware/       # stack.py registers everything in order
├── store/            # KeyValueStore protocol + InMemoryStore
├── routes/           # operational routes only: /live, /health, /metrics
├── log/ metrics/ telemetry/
├── domains/<name>/   # business logic, one package per bounded context
└── services/<name>/  # ASGI apps: main.py, domains.py (DOMAINS list), Dockerfile
scripts/              # new_domain.py (scaffold), generate_openapi.py
tests/                # global/{unit,integration}, domains/<name>/{unit,integration,fuzz}, scripts/
```

## Domains

Business features are domains. Create one with `make domain DOMAIN=<snake_case>`, then
customise; don't hand-write the files. Each layer depends only on the one below:

```
KeyValueStore (protocol) → Repository → Service → Domain (routes + bootstrap)
```

| File | Holds | Never |
| --- | --- | --- |
| `models.py` | Pydantic entity + request models | logic, I/O |
| `errors.py` | `<Entity>ErrorCode` (StrEnum) + `<Entity>Error(DomainError[...])` with `STATUS` | HTTP objects |
| `repository.py` | store calls; takes `KeyValueStore[K, V]` (the protocol, not a concrete store) | business rules |
| `service.py` | business rules; methods return `Result[T, <Entity>Error]`, take `ctx: RequestContext` last | raising for domain errors, `Request`/HTTP access |
| `dependencies.py` | `<Entity>ServiceDep` via `get_domain()` | instantiating services or stores |
| `domain.py` | `<Plural>Domain` container, `ResultRouter` routes, `make_router()`, `bootstrap()` | business logic |

**Contract** (checked by `create_app()`, see `src/bootstrap.py`). A domain module exposes any of:

- `make_router() -> APIRouter` — returns the module-level router; mounted under `API_PREFIX` (`/v1`).
- `async bootstrap(boot: BootstrapContext) -> <Plural>Domain` — the only place a concrete store
  or client is created. `boot` has `settings`, `audit_backend`, `audit_integrity`, `extra`
  (the `extra_context` dict). Each domain returns a distinct type.
- `<Plural>Domain.aclose()` (optional) — awaited on shutdown in reverse order, and when a later
  bootstrap fails. Close whatever `bootstrap()` opened.
- `register_exception_handlers(app)` (optional) — not needed for `DomainError`.

Register a domain by listing it in `src/services/<service>/domains.py` (the scaffold does this).

**Errors.** A route on a `ResultRouter` returns the service `Result` unchanged.
`Success(v)` becomes the body (`response_model` is inferred from `Result[T, ...]`);
`Failure(error)` becomes an RFC 9457 problem with `status` from `<Entity>Error.STATUS`
(unmapped codes → 500) and `code` as an extension member. For 5xx the client sees only the
reason phrase; the message is logged. Outside domains, raise `AppError` subclasses
(`NotFoundError`, `ConflictError`, …) or `HTTPException`. Every error body is
`application/problem+json` with `type`, `title`, `status`, `detail`, `instance`, `request_id`.

**Audit.** State-changing service methods emit an event, failures included:
`await log_operation(backend, integrity, ctx, "orders.create", resource_id=order.id)`.

## Gotchas

These are the mistakes agents make most often here:

1. **No `from __future__ import annotations`.** Annotations are lazy on 3.14+ (PEP 649); Ruff bans it.
2. **Annotations FastAPI reads must be real imports.** In route modules (`domain.py`,
   `dependencies.py`, `routes/`, `deps.py`), names used in route/dependency signatures and
   `-> Result[...]` return types must be imported at module level, not under `if TYPE_CHECKING:`.
   Otherwise FastAPI silently treats a body model as a required query parameter (every request
   gets a 422). `create_app()` refuses to start when a domain route has one, and `ResultRouter`
   raises at the decorator; both errors name the annotation and the fix. Ruff's `TC` rules are disabled
   for those files so `--fix` won't move such imports. Everywhere else, typing-only imports
   *do* go under `TYPE_CHECKING` (Ruff enforces it).
3. **Services return `Failure(...)`; they don't raise** for not-found, conflict, or storage errors.
   Catch storage exceptions only around the repository call (`# noqa: BLE001 — storage boundary`).
4. **Tests need the lifespan.** A hand-built `AsyncClient` without `LifespanManager` leaves domains
   unbootstrapped, and every domain dependency raises `LookupError`. Use the fixtures below.
5. **Every `Settings` field must appear in `.env.example`** — a test fails otherwise. Secrets are
   `SecretStr`; call `.get_secret_value()` only at the point of use.
6. **`make check` rewrites files** and doesn't run tests; `make verify` is the gate.

## Tests

Three tiers per domain: `tests/domains/<name>/unit/` (service/repository, `MagicMock` ctx),
`integration/` (HTTP via `client`), `fuzz/` (Hypothesis `@given`). Fixtures in `tests/conftest.py`:

- `client` — HTTP client for an app serving every domain in `services/api/domains.py`.
- `make_app(settings={...}, **create_app_kwargs)` — custom app (no-op audit backend, no domains by default).
- `async with make_client(app, raise_app_exceptions=False) as c:` — client with the lifespan running.
- `make_settings(**overrides)` / `test_settings` — test settings; a local `.env` is never read.

Pytest turns warnings into errors and uses strict markers; `asyncio_mode = "auto"`.

## Extension points (`create_app(...)` keyword arguments)

| Argument | Contract |
| --- | --- |
| `auth_provider` | `AuthProvider`: `async authenticate(request) -> principal \| None` and `async authorize(request, principal, ctx) -> bool`. Protect routes with `Depends(get_auth_context)` |
| `audit_backend` | `AuditBackend` subclass with `async log(event)`; default Loguru JSON |
| `audit_integrity` | `SequenceIntegrity` / `ChecksumIntegrity` / `CombinedIntegrity` for tamper evidence |
| `health_checks` | async callables returning `{"name": str, "healthy": bool}`; `/health` → 503 if any fail |
| `rate_limit_storage` | any `limits.aio.storage.Storage` (default in-process `MemoryStorage`; fails open) |
| `extra_context` | dict set on `app.state` and passed to bootstraps as `boot.extra` |
| `domains` | domain modules (see above) |

Custom metrics: `metrics.registry.counter("orders_total", "help", ["status"])`.
Per-request context: `RequestContextDep` or `request.state.ctx` (`request_id`, `set`, `get`).

## Configuration

All settings are in `src/config.py` and documented in `.env.example`. List settings accept
`a,b` or `["a","b"]`. In `production`, logs are JSON, `/docs` is off and unhandled exceptions return
a sanitised 500. Middleware order (outer → inner): TrustedHost → CORS → InFlight → Audit →
SecurityHeaders → Timeout → SizeLimit → RateLimit → Context → handler.
Built-in routes `/live`, `/health`, `/metrics`, `/docs` are never prefixed.

## Conventions

- Line length 100; Ruff only. Never a bare `except:`; a broad `except Exception` needs a `noqa` reason.
- Relative imports inside a domain package (`from .models import ...`).
- Don't add docstrings, comments or annotations to code you didn't change; don't add unrequested features.
- Commits and PR titles follow Conventional Commits with the scopes in `.github/conventional-commits.yml`.
