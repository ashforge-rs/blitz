# syntax=docker/dockerfile:1
# ────────────────────────────────────────────────
# Stage 1: builder — install dependencies via uv
# ────────────────────────────────────────────────
FROM python:3.15-slim AS builder

# Pinned uv (must satisfy [tool.uv] required-version; Dependabot bumps it).
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/

# UV_COMPILE_BYTECODE — precompile .pyc at build time for faster cold starts.
# UV_LINK_MODE=copy   — required with the cache mount (different filesystem).
# UV_PYTHON_DOWNLOADS — always use the image's interpreter, never download one.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Layer-cache: install deps before copying source so this layer only
# invalidates when pyproject.toml / uv.lock change. The cache mount keeps
# downloaded wheels across builds without baking them into the image.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
 && python -m compileall -q src

# ────────────────────────────────────────────────
# Stage 2: runtime — minimal production image
# ────────────────────────────────────────────────
FROM python:3.15-slim AS runtime

LABEL org.opencontainers.image.title="blitz-api" \
      org.opencontainers.image.description="blitz FastAPI service"

RUN useradd --system --no-create-home --uid 1001 appuser

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src   /app/src

# UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN — on SIGTERM uvicorn stops accepting new
# connections and waits this long for in-flight requests. Keep it at or below
# your orchestrator's termination grace period (Kubernetes default: 30s).
# Workers: set WEB_CONCURRENCY (read natively by uvicorn); default is 1.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=25

WORKDIR /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/live')"

CMD ["uvicorn", "services.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--no-access-log"]
