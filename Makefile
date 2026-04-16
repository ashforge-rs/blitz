.PHONY: install dev dev-api lint fmt check test test-unit test-integration test-fuzz coverage openapi docker-build docker-push docker-run clean

install:
	uv sync

# ── Multi-service development ─────────────────────────────────────────────────
# Each service lives under src/services/<name>/main.py and exposes an ASGI app.
# Shared library code lives in src/ (app.py, config.py, audit/, middleware/, …).
#
# To run a specific service:
#   make dev SERVICE=api         (default)
#   make dev SERVICE=worker      (once src/services/worker/main.py exists)
#
# PYTHONPATH is always src/ so all shared modules are importable unqualified.
# ---------------------------------------------------------------------------

SERVICE_NAME ?= api

dev: dev-api

dev-api:
	uv run uvicorn services.api.main:app --reload --app-dir src

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

check: fmt lint
	uv run mypy src/

test:
	uv run pytest -v

test-unit:
	uv run pytest tests/global/unit/ tests/domains/*/unit/ -v

test-integration:
	uv run pytest tests/global/integration/ tests/domains/*/integration/ -v

test-fuzz:
	uv run pytest tests/domains/*/fuzz/ -v

coverage:
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=80

openapi:
	uv run python scripts/generate_openapi.py

# ── Docker helpers ────────────────────────────────────────────────────────────
# Usage:
#   make docker-build SERVICE=api          # build the api service image
#   make docker-push  SERVICE=api          # build + push to GHCR
#   make docker-run   SERVICE=api PORT=8000 # run locally

SERVICE ?= api
PORT    ?= 8000
IMAGE   ?= ghcr.io/$(shell git config --get remote.origin.url | sed 's/.*github.com[:/]//' | sed 's/\.git$$//' | tr '[:upper:]' '[:lower:]')-$(SERVICE)

docker-build:
	docker build \
		--file src/services/$(SERVICE)/Dockerfile \
		--tag blitz-$(SERVICE):local \
		--cache-from type=registry,ref=$(IMAGE):buildcache \
		.

docker-push:
	docker build \
		--file src/services/$(SERVICE)/Dockerfile \
		--tag $(IMAGE):latest \
		--tag $(IMAGE):sha-$(shell git rev-parse --short HEAD) \
		--cache-from type=registry,ref=$(IMAGE):buildcache \
		--cache-to   type=registry,ref=$(IMAGE):buildcache,mode=max \
		--push \
		.

docker-run:
	docker run --rm -p $(PORT):8000 \
		--env-file .env \
		blitz-$(SERVICE):local

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .venv dist build htmlcov coverage.xml .coverage
