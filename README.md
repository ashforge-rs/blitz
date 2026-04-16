# blitz

FastAPI boilerplate

[![CI](https://github.com/ashforge-rs/blitz/actions/workflows/ci.yml/badge.svg)](https://github.com/ashforge-rs/blitz/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Overview

Blitz is a FastAPI project template designed for teams that want a clean starting point without spending time wiring up the basics. It ships with an opinionated but flexible architecture, a full middleware stack, structured logging, Prometheus metrics, OpenTelemetry tracing, and a test suite — all ready to extend.

**Stack:** FastAPI, Pydantic v2, Uvicorn, Loguru, prometheus-client, OpenTelemetry, uv, Ruff, mypy

---

## Quick start

```bash
git clone https://github.com/ashforge-rs/blitz.git
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
  middleware/     # Security, rate limiting, timeout, audit, context
  auth/           # AuthProvider protocol — plug in any auth scheme
  audit/          # Structured audit trail with pluggable backends
  routes/         # Built-in: /live  /health  /metrics
  example/        # Reference domain — service / repository / store layers
tests/
  unit/           # Service and repository unit tests
  integration/    # Full HTTP route tests with lifespan
  fuzz/           # Hypothesis-based property tests
```

---

## Adding a domain

Each feature area follows a four-layer pattern:

```
InMemoryStore  ->  Repository  ->  Service  ->  Domain (router + bootstrap)
```

Register it in `src/main.py`:

```python
from orders import domain as orders_domain

app = create_app(domains=[orders_domain])
```

`bootstrap(settings)` is called once at startup; `make_router()` is called at application creation. See `src/example/` for a complete working implementation.

---

## Configuration

All settings are read from environment variables or a `.env` file. See `.env.example` for the full reference.

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `production` / `test` |
| `LOG_LEVEL` | `INFO` | Loguru log level |
| `WORKERS` | `1` | Uvicorn worker count |
| `RATE_LIMIT` | `100/minute` | Per-IP sliding window limit |
| `REQUEST_TIMEOUT_SECONDS` | `30.0` | Per-request hard timeout |
| `MAX_REQUEST_SIZE_BYTES` | `10485760` | 10 MB body limit |
| `ALLOWED_ORIGINS` | `["*"]` | CORS allowed origins |
| `CORS_ALLOW_CREDENTIALS` | `false` | Requires explicit origins — wildcard is rejected |
| `TRUSTED_PROXIES` | `[]` | CIDRs of trusted reverse proxies for XFF resolution |
| `OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `OTEL_ENDPOINT` | `""` | OTLP HTTP collector URL |
| `METRICS_ENDPOINT_ENABLED` | `true` | Expose `/metrics` |

---

## Built-in endpoints

| Endpoint | Description |
|---|---|
| `GET /live` | Liveness probe — always `200 {"status":"ok"}` |
| `GET /health` | Readiness — `200` / `503` based on registered health checks |
| `GET /metrics` | Prometheus exposition format |
| `GET /docs` | Swagger UI (development only) |

---

## Development commands

| Command | Description |
|---|---|
| `make install` | Install all dependencies via `uv sync` |
| `make dev` | Start dev server with hot-reload |
| `make check` | Format and lint with Ruff |
| `make test` | Run pytest |
| `make coverage` | Run pytest with HTML coverage report |
| `uv run mypy src/` | Type-check |

---

## Extension points

- **Authentication:** implement `AuthProvider` and pass it to `create_app(auth_provider=...)`. Protect routes with `Depends(get_auth_context)`.
- **Audit backend:** implement `AuditBackend` and pass it to `create_app(audit_backend=...)`. Default writes structured JSON via Loguru.
- **Health checks:** pass async callables to `create_app(health_checks=[...])`.
- **Rate limit storage:** pass any `limits.storage.Storage` to `create_app(rate_limit_storage=...)`. Default is in-memory; use Redis for multi-worker deployments.
- **Metrics:** use `metrics.registry.counter` / `gauge` / `histogram` to register custom Prometheus metrics.
- **Tracing:** set `OTEL_ENABLED=true` and `OTEL_ENDPOINT` to send traces to any OTLP-compatible collector (Jaeger, Grafana Tempo, Honeycomb, Datadog).

---

## Testing

```bash
make test                          # all tests
uv run pytest tests/unit/          # unit only
uv run pytest tests/integration/   # integration only
uv run pytest tests/fuzz/          # Hypothesis fuzz tests
```

Coverage is enforced at 80 % in CI.

---

## Deployment

A `Dockerfile` and `docker-compose.yml` are included. A Grafana dashboard with Prometheus data source is pre-configured under `grafana/`.

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
- Matrix: Python 3.12 and 3.13

Releases are automated via [release-please](https://github.com/googleapis/release-please). Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) — the PR title check enforces this automatically.

---

## License

MIT

---

_This project was scaffolded and refined with the assistance of GitHub Copilot powered by Claude Sonnet 4.6._
