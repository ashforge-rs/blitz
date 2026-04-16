Generate an optimal multi-stage Dockerfile for this blitz application.

Arguments: $ARGUMENTS

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

3. Read `src/services/api/main.py` to confirm the uvicorn entry point (`module:app` string).

4. Check whether a `.dockerignore` exists; if not, create one (see below).

Then produce a Dockerfile with these exact characteristics:

### Dockerfile structure

**Stage 1 — `builder`**

```
FROM python:3.XX-slim AS builder
```

- Pin to the exact Python minor version from `requires-python`
- Copy uv binary from the official image:
  ```
  COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
  ```
- Set workdir to `/app`
- Copy `pyproject.toml` and `uv.lock` first (layer-cache friendly)
- Run `uv sync --frozen --no-dev --no-install-project` to install deps only
- Copy source code (`src/`) and run `uv sync --frozen --no-dev` to install the project itself
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
- Switch to non-root user: `USER appuser`
- Expose port 8000 (or the configured port)
- Add a `HEALTHCHECK` using `/live` endpoint
- Use `CMD` with `uvicorn` directly (not the `main()` entrypoint) so Docker signals are handled correctly:
  ```
  CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000",
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
dist/
build/
*.egg-info/
.env
.env.*
!.env.example
tests/
```

### Output

Write the Dockerfile to the repo root. If a Dockerfile already exists, show a diff of proposed changes and ask before overwriting.

After writing:

1. Run `docker build --no-cache -t <name>:dev .` if docker is available, to validate the build.
2. Print a summary table of image optimisation choices made.

## Conventions

- Never use `COPY . .` in the builder — always copy `pyproject.toml`/`uv.lock` separately first for caching
- Never run as root in the runtime stage
- Never include dev dependencies, test files, or `.env` secrets in the image
- Prefer `CMD` (exec form) over `ENTRYPOINT` for simpler signal handling
- Use `--frozen` with `uv sync` to ensure reproducible builds from `uv.lock`
