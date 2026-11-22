# Changelog

## 0.3.0 (2026-11-22)


### ⚠ BREAKING CHANGES

* **domains:** `bootstrap()` takes a typed `BootstrapContext` (`boot.settings`, `boot.audit_backend`, `boot.audit_integrity`, `boot.extra`) instead of `**kwargs`. `create_app()` validates every domain module, and two domains returning the same type are rejected.
* **log:** logs are flat JSON lines in every environment; set `LOG_FORMAT=text` for coloured local output. The domain-failure log binds the error text as `error` instead of `message`.
* **config:** `python -m services.api.main` listens on `HOST`/`PORT`, and the default host is now `127.0.0.1` (the Docker images are unaffected).
* `src/main.py` and the root `Dockerfile` are gone: use `services.<name>.main:app` and `src/services/<name>/Dockerfile`.
* `scripts/new_domain.py` is replaced by the `blitz` CLI; `make domain` keeps working.


### Features

* **cli:** `blitz`, a code generator in `cli/` (its own uv project): domains and services from template files, project templates overriding built-in ones, `domain list|remove`
* **cli:** `crud` wizard generating an entity with real fields (`-f title:str -f notes:str?`)
* **cli:** `g endpoint` and `g error-code` for existing domains; `g auth-provider|audit-backend|health-check|middleware|route|metric` created and wired; `blitz add redis|postgres [--domain]`
* **cli:** `routes`, `openapi --diff REF --check` with breaking-change detection, `doctor`, shell completion, and `blitz new` / `blitz update` (three-way merge of later boilerplate changes)
* **domains:** `ResultRouter` turns `Failure(DomainError)` into an RFC 9457 response; shared `RequestContextDep`, `SettingsDep` and audit deps; `log_operation`; domains with `aclose()` are closed on shutdown
* **routes:** startup fails on route annotations FastAPI cannot resolve, naming the annotation and the fix
* **config:** `HOST`/`PORT` settings; a test keeps `.env.example` in sync with `Settings`; `make_settings` / `make_app` / `make_client` test fixtures
* `make verify`: one non-mutating check of format, lint, types and tests
* **examples:** `examples/todo`, a layered high-integrity app on SQLAlchemy, Alembic and Postgres with an observable audit outbox; `examples/consent`, the lean variant; demo seeds and Grafana dashboards


### Bug Fixes

* **cli:** generator edits stay valid Python with trailing comments and write all or nothing; `domain remove` rejects paths; `REDIS_URL` is a `SecretStr`; `openapi --diff` flags tighter request constraints
* **services:** the compose dev setup builds the per-service Dockerfile and runs
* the coverage table renders only for coverage runs; `make dev` honours `SERVICE` and `PORT`
* **examples:** gap-free audit sequences on retry; expired idempotency records are purged
* **examples:** no flaky "Event loop is closed" after a failed SQLite connect; no duplicate outbox delivery on shutdown


### Documentation

* ADR 0001: flat domains by default, the layered pattern for high-integrity services
* `AGENTS.md` is the single source of agent rules; a test checks that agent docs reference real paths


### Build System

* wheel contents and first-party modules are derived from `src/`
* **examples:** standalone uv projects


### Code Refactoring

* **examples:** one shared implementation of each piece of context

## 0.2.0 (2026-11-20)


### ⚠ BREAKING CHANGES

* Domain routes are mounted under `API_PREFIX` (default `/v1`): `/example/` → `/v1/example/`. Set `API_PREFIX=""` to keep the old paths.
* All error responses are RFC 9457 Problem Details (`application/problem+json`). `detail` is still present.
* `create_app(rate_limit_storage=...)` takes a `limits.aio.storage.Storage` (async) instead of `limits.storage.Storage`.
* Python 3.15+ is required (`requires-python = ">=3.15"`).


### Features

* RFC 9457 problem details, `/v1` API prefix, `OTEL_HEADERS` secret setting


### Bug Fixes

* **middleware:** timeout no longer sends a second response start; malformed `Content-Length` returns 400; `Retry-After` is in seconds; `TRUSTED_PROXIES` is applied; unsafe `X-Request-ID` values are replaced
* **config:** list settings accept comma-separated values; `.env.example` no longer crashes startup
* **log:** `--no-access-log` is respected; requests are no longer logged twice


### Build System

* upgrade to Python 3.15
* **deps:** bump Python and GitHub Actions dependencies
* stricter lint, test and pre-commit tooling
* **docker:** pinned uv, cached and precompiled builds, graceful shutdown


### Continuous Integration

* least-privilege token, SHA-pinned actions, dependency audit
* **deps:** valid Dependabot commit titles, single uv version source


### Code Refactoring

* drop `__future__` annotations and type the domain lookup

## 0.1.1 (2026-10-03)


### Features

* **telemetry:** use FastAPI native OpenTelemetry support


### Bug Fixes

* **middleware:** set request context through request.state


### Build System

* **deps:** upgrade runtime and dev dependencies
* use python 3.12 base image
