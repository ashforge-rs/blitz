Generate an optimal multi-stage Dockerfile for one blitz service.

Arguments: $ARGUMENTS

The argument is the service name (default `api`). Each service owns its image at
`src/services/<service>/Dockerfile`; CI, `make docker-build SERVICE=<service>` and
`docker-compose.yml` all build from that path with the repo root as build context. There is
no root Dockerfile.

## Instructions

Gather context from the project before writing the Dockerfile:

1. Read `pyproject.toml` to get:
   - `requires-python` → Python version
   - `[project] name` → image label / app name
   - `[project] version` → image label
   - `dependencies` list → nothing to change, UV handles this
   - `[dependency-groups] dev` → confirm they are excluded from the production image

2. Read `src/config.py` to confirm:
   - Default `PORT` (check for a PORT setting; fall back to 8000)
   - Default `WORKERS` setting value

3. Read `src/services/<service>/main.py` to confirm the uvicorn entry point
   (`services.<service>.main:app`). If an image already exists for another service
   (e.g. `src/services/api/Dockerfile`), keep the new one consistent with it.

4. Check whether a `.dockerignore` exists; if not, create one (see below).

Then produce a Dockerfile with these exact characteristics:

### Dockerfile structure

**Stage 1 — `builder`**

```
FROM python:3.XX-slim AS builder
```

- Pin to the exact Python minor version from `requires-python`
- Copy the uv binary from the official image, **pinned** to the version in `[tool.uv] required-version`
  (never `:latest`):
  ```
  COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/
  ```
- Set `ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0`
- Set workdir to `/app`
- Copy `pyproject.toml` and `uv.lock` first (layer-cache friendly)
- Run `uv sync --frozen --no-dev --no-install-project` to install deps only, with
  `RUN --mount=type=cache,target=/root/.cache/uv`
- Copy source code (`src/`) and run `uv sync --frozen --no-dev` (same cache mount), then
  `python -m compileall -q src`
- This keeps the virtualenv at `/app/.venv`

**Stage 2 — `runtime`**

```
FROM python:3.XX-slim AS runtime
```

- Same Python version as builder
- Create a non-root user: `RUN useradd --system --no-create-home appuser`
- Copy only the virtualenv from builder: `COPY --from=builder /app/.venv /app/.venv`
- Copy the installed package: `COPY --from=builder /app/src /app/src`
- Set `ENV PATH="/app/.venv/bin:$PATH"` and `PYTHONPATH="/app/src"`
- Set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`
- Set `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN` (default `25`) — at or below the orchestrator's
  termination grace period so in-flight requests drain on SIGTERM
- Switch to non-root user: `USER appuser`
- Expose port 8000 (or the configured port)
- Add a `HEALTHCHECK` using `/live` endpoint
- Use `CMD` with `uvicorn` directly (not the `main()` entrypoint) so Docker signals are handled correctly:
  ```
  CMD ["uvicorn", "services.<service>.main:app", "--host", "0.0.0.0", "--port", "8000",
       "--loop", "uvloop", "--http", "httptools", "--no-access-log"]
  ```
  Do NOT hardcode `--workers` — let it be set via `WEB_CONCURRENCY` env var or the `WORKERS` setting.

### Labels

Add OCI-standard image labels:

```
LABEL org.opencontainers.image.title="<app name>"
LABEL org.opencontainers.image.version="<version>"
LABEL org.opencontainers.image.description="FastAPI application"
```

### .dockerignore (create if missing)

```
.venv/
.git/
.gitignore
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
.mypy_cache/
.hypothesis/
dist/
build/
*.egg-info/
.env
.env.*
!.env.example
.github/
.claude/
openspec/
infra/
grafana/
scripts/
tests/
*.md
```

### Output

Write the Dockerfile to `src/services/<service>/Dockerfile`. If it already exists, show a diff of
proposed changes and ask before overwriting. `.dockerignore` stays at the repo root (shared by
every service).

After writing:

1. Run `make docker-build SERVICE=<service>` if docker is available, to validate the build.
2. Print a summary table of image optimisation choices made.

## Conventions

- Never use `COPY . .` in the builder — always copy `pyproject.toml`/`uv.lock` separately first for caching
- Never run as root in the runtime stage
- Never include dev dependencies, test files, or `.env` secrets in the image
- Prefer `CMD` (exec form) over `ENTRYPOINT` for simpler signal handling
- Use `--frozen` with `uv sync` to ensure reproducible builds from `uv.lock`
