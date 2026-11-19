# Changelog

## [0.2.0](https://github.com/ashforge-rs/blitz/compare/v0.1.1...v0.2.0) (2026-11-20)


### ⚠ BREAKING CHANGES

* Domain routes are mounted under `API_PREFIX` (default `/v1`): `/example/` → `/v1/example/`. Set `API_PREFIX=""` to keep the old paths.
* All error responses are RFC 9457 Problem Details (`application/problem+json`). `detail` is still present.
* `create_app(rate_limit_storage=...)` takes a `limits.aio.storage.Storage` (async) instead of `limits.storage.Storage`.
* Python 3.15+ is required (`requires-python = ">=3.15"`).


### Features

* RFC 9457 problem details, `/v1` API prefix, `OTEL_HEADERS` secret setting ([0e522c4](https://github.com/ashforge-rs/blitz/commit/0e522c4))


### Bug Fixes

* **middleware:** timeout no longer sends a second response start; malformed `Content-Length` returns 400; `Retry-After` is in seconds; `TRUSTED_PROXIES` is applied; unsafe `X-Request-ID` values are replaced ([af82af7](https://github.com/ashforge-rs/blitz/commit/af82af7))
* **config:** list settings accept comma-separated values; `.env.example` no longer crashes startup ([af82af7](https://github.com/ashforge-rs/blitz/commit/af82af7))
* **log:** `--no-access-log` is respected; requests are no longer logged twice ([e95d903](https://github.com/ashforge-rs/blitz/commit/e95d903))


### Build System

* upgrade to Python 3.15 ([158e254](https://github.com/ashforge-rs/blitz/commit/158e254))
* **deps:** bump Python and GitHub Actions dependencies ([9e0c4e4](https://github.com/ashforge-rs/blitz/commit/9e0c4e4))
* stricter lint, test and pre-commit tooling ([973834e](https://github.com/ashforge-rs/blitz/commit/973834e))
* **docker:** pinned uv, cached and precompiled builds, graceful shutdown ([f1a63e6](https://github.com/ashforge-rs/blitz/commit/f1a63e6))


### Continuous Integration

* least-privilege token, SHA-pinned actions, dependency audit ([4cc81a0](https://github.com/ashforge-rs/blitz/commit/4cc81a0))
* **deps:** valid Dependabot commit titles, single uv version source ([b3031c6](https://github.com/ashforge-rs/blitz/commit/b3031c6))


### Code Refactoring

* drop `__future__` annotations and type the domain lookup ([e655dbf](https://github.com/ashforge-rs/blitz/commit/e655dbf))

## [0.1.1](https://github.com/ashforge-rs/blitz/compare/cb38989...v0.1.1) (2026-10-03)


### Features

* **telemetry:** use FastAPI native OpenTelemetry support ([d55222a](https://github.com/ashforge-rs/blitz/commit/d55222a))


### Bug Fixes

* **middleware:** set request context through request.state ([8caef0f](https://github.com/ashforge-rs/blitz/commit/8caef0f))


### Build System

* **deps:** upgrade runtime and dev dependencies ([c8c931a](https://github.com/ashforge-rs/blitz/commit/c8c931a))
* use python 3.12 base image ([4d9b05a](https://github.com/ashforge-rs/blitz/commit/4d9b05a))
