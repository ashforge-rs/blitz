# syntax=docker/dockerfile:1
# ────────────────────────────────────────────────
# Stage 1: builder — install dependencies via uv
# ────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Layer-cache: install deps before copying source so this layer only
# invalidates when pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-dev

# ────────────────────────────────────────────────
# Stage 2: runtime — minimal production image
# ────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN useradd --system --no-create-home --uid 1001 appuser

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src   /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production

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
