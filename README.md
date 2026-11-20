# blitz

FastAPI boilerplate

[![CI](https://github.com/YOUR_ORG/YOUR_REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/YOUR_REPO/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.15-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Overview

Blitz is a FastAPI project template designed for teams that want a clean starting point without spending time wiring up the basics. It ships with an opinionated but flexible architecture, a full middleware stack, structured logging, Prometheus metrics, OpenTelemetry tracing, and a test suite — all ready to extend.

**Stack:** FastAPI, Pydantic v2, Uvicorn, Loguru, prometheus-client, OpenTelemetry, uv, Ruff, mypy

---

## Quick start

```bash
git clone https://github.com/YOUR_ORG/YOUR_REPO.git
cd blitz
cp .env.example .env
make install
make dev
```

The API is available at `http://localhost:8000`. Interactive docs are at `/docs` (disabled in production).

---

## Project structure

```
src/
  app.py          # Application factory — primary extension point
  config.py       # All settings via pydantic-settings (.env / env vars)
  lifespan.py     # Startup and graceful-shutdown lifecycle
  service.py      # Base Service class — extend for every domain service
  store/          # KeyValueStore protocol + InMemoryStore implementation
  middleware/     # Security, rate limiting, timeout, audit, context
  auth/           # AuthProvider protocol — plug in any auth scheme
  audit/          # Structured audit trail with pluggable backends
  telemetry/      # OpenTelemetry tracing initialisation
  routes/         # Built-in: /live  /health  /metrics
  domains/        # Bounded-context business logic (one sub-package per domain)
    example/      # Reference domain — models / repository / service / domain / dependencies
  services/       # Independent ASGI application instances
    api/          # Default service — wires domains into an ASGI app
      main.py     # create_app() call + uvicorn entry point
      Dockerfile  # Per-service container image
tests/
  conftest.py     # Global fixtures (make_settings, make_app, make_client, app, client)
  global/         # Framework-level tests (no domain dependency)
    unit/         # InMemoryStore and other infrastructure unit tests
    integration/  # App-wide integration tests (middleware, auth, errors)
  domains/        # Per-domain tests — mirrors src/domains/ layout
    example/
      unit/       # Service and repository unit tests
      integration/# HTTP route tests with full ASGI lifespan
      fuzz/       # Hypothesis property-based tests
```

---

## Adding a domain

Each feature area follows a four-layer pattern:

```
InMemoryStore  ->  Repository  ->  Service  ->  Domain (router + bootstrap)
```

Scaffold one, with tests, and register it with the `api` service:

```bash
make domain DOMAIN=orders        # entity: Order; routes at /v1/orders
```

Registered domains are listed in `src/services/api/domains.py`. `make_router()` is called at application creation; `async bootstrap(boot)` is called once at startup and may return an instance with `aclose()` for shutdown. Services return `Result[T, DomainError]`, and `ResultRouter` maps failures to RFC 9457 responses. See `CLAUDE.md` for the contract and `src/domains/example/` for a complete working implementation.

---

## Configuration

All settings are read from environment variables or a `.env` file. See `.env.example` for the full reference.

| Variable                   | Default       | Description                                         |
| -------------------------- | ------------- | --------------------------------------------------- |
| `ENVIRONMENT`              | `development` | `development` / `production` / `test`               |
| `LOG_LEVEL`                | `INFO`        | Loguru log level                                    |
| `WORKERS`                  | `1`           | Uvicorn worker count                                |
| `HOST` / `PORT`            | `127.0.0.1` / `8000` | Bind address for `python -m services.api.main` |
| `RATE_LIMIT`               | `100/minute`  | Per-IP sliding window limit                         |
| `REQUEST_TIMEOUT_SECONDS`  | `30.0`        | Per-request hard timeout                            |
| `MAX_REQUEST_SIZE_BYTES`   | `10485760`    | 10 MB body limit                                    |
| `ALLOWED_ORIGINS`          | `["*"]`       | CORS allowed origins                                |
| `CORS_ALLOW_CREDENTIALS`   | `false`       | Requires explicit origins — wildcard is rejected    |
| `TRUSTED_PROXIES`          | `[]`          | CIDRs of trusted reverse proxies for XFF resolution |
| `OTEL_ENABLED`             | `false`       | Enable OpenTelemetry tracing                        |
| `OTEL_ENDPOINT`            | `""`          | OTLP HTTP collector URL                             |
| `OTEL_HEADERS`             | `""`          | OTLP auth headers `k=v,k2=v2` (secret, masked)      |
| `API_PREFIX`               | `/v1`         | Prefix for domain routes (`""` disables)            |
| `METRICS_ENDPOINT_ENABLED` | `true`        | Expose `/metrics`                                   |

---

## Built-in endpoints

| Endpoint       | Description                                                 |
| -------------- | ----------------------------------------------------------- |
| `GET /live`    | Liveness probe — always `200 {"status":"ok"}`               |
| `GET /health`  | Readiness — `200` / `503` based on registered health checks |
| `GET /metrics` | Prometheus exposition format                                |
| `GET /docs`    | Swagger UI (development only)                               |

Domain routes are served under `API_PREFIX` (default `/v1`, e.g. `/v1/example/`). All errors are
RFC 9457 Problem Details (`application/problem+json`) with `type`, `title`, `status`, `detail`,
`instance` and `request_id`.

---

## Development commands

| Command                 | Description                                                |
| ----------------------- | ---------------------------------------------------------- |
| `make install`          | Install all dependencies via `uv sync`                     |
| `make help`             | List every target                                          |
| `make dev`              | Start dev server with hot-reload (`SERVICE=api`, `PORT=8000`) |
| `make domain DOMAIN=x`  | Scaffold a domain + tests and register it                  |
| `make check`            | Format and lint with Ruff, then type-check with mypy       |
| `make test`             | Run all tests                                              |
| `make test-unit`        | Unit tests only (global + all domains)                     |
| `make test-integration` | Integration tests only (global + all domains)              |
| `make test-fuzz`        | Hypothesis fuzz tests for all domains                      |
| `make coverage`         | Run pytest with HTML coverage report                       |
| `uv run mypy src/`      | Type-check                                                 |

---

## Extension points

- **Authentication:** implement `AuthProvider` and pass it to `create_app(auth_provider=...)`. Protect routes with `Depends(get_auth_context)`.
- **Audit backend:** implement `AuditBackend` and pass it to `create_app(audit_backend=...)`. Default writes structured JSON via Loguru.
- **Health checks:** pass async callables to `create_app(health_checks=[...])`.
- **Rate limit storage:** pass any async `limits.aio.storage.Storage` to `create_app(rate_limit_storage=...)`. Default is in-memory; use Redis for multi-worker deployments.
- **Metrics:** use `metrics.registry.counter` / `histogram` to register custom Prometheus metrics.
- **Tracing:** set `OTEL_ENABLED=true` and `OTEL_ENDPOINT` to send traces to any OTLP-compatible collector (Jaeger, Grafana Tempo, Honeycomb, Datadog).

---

## Testing

```bash
make test                  # all tests
make test-unit             # unit tests only (global + all domains)
make test-integration      # integration tests only (global + all domains)
make test-fuzz             # Hypothesis fuzz tests for all domains

# Target a specific domain or layer directly:
uv run pytest tests/domains/example/unit/
uv run pytest tests/domains/example/integration/
uv run pytest tests/domains/example/fuzz/
uv run pytest tests/global/
```

Coverage is enforced at 80 % in CI.

---

## Deployment

Each service ships its own image definition (`src/services/<name>/Dockerfile`), and `docker-compose.yml` runs the `api` service with Prometheus and Grafana. A Grafana dashboard with Prometheus data source is pre-configured under `grafana/`.

Set `ENVIRONMENT=production` to enable:

- JSON-structured logging
- Sanitised 500 error responses (no stack traces in responses)
- HSTS header on all responses
- Disabled Swagger UI

---

## CI

GitHub Actions runs on every push and pull request:

- Ruff format check and lint
- mypy type-check
- pytest with coverage enforcement (>= 80 %)
- Matrix: Python 3.15

Releases are automated via [release-please](https://github.com/googleapis/release-please). Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) — the PR title check enforces this automatically.

---

## License

MIT

---

_This project was scaffolded and refined with the assistance of GitHub Copilot powered by Claude Sonnet 4.6._
