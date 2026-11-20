.DEFAULT_GOAL := help
.PHONY: help install dev domain lint fmt check test test-unit test-integration test-fuzz coverage openapi docker-build docker-push docker-run clean

# ── Multi-service layout ──────────────────────────────────────────────────────
# Each service lives under src/services/<name>/ (main.py + Dockerfile) and
# exposes an ASGI `app`. Shared library code lives in src/. Every target that
# deals with a service takes SERVICE=<name> (default: api):
#
#   make dev SERVICE=worker      (once src/services/worker/main.py exists)
#
# PYTHONPATH is always src/ so all shared modules are importable unqualified.
# ──────────────────────────────────────────────────────────────────────────────

SERVICE ?= api
PORT    ?= 8000
IMAGE   ?= ghcr.io/$(shell git config --get remote.origin.url | sed 's/.*github.com[:/]//' | sed 's/\.git$$//' | tr '[:upper:]' '[:lower:]')-$(SERVICE)

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install all dependencies (uv sync)
	uv sync

dev: ## Run a service with hot-reload (SERVICE=api, PORT=8000)
	uv run uvicorn services.$(SERVICE).main:app --reload --app-dir src --port $(PORT)

domain: ## Scaffold a domain + tests and register it (DOMAIN=orders [ENTITY=Order] [SERVICE=api])
	@test "$(origin DOMAIN)" = "command line" || \
		(echo "usage: make domain DOMAIN=<snake_case> [ENTITY=<PascalCase>] [SERVICE=api]" && exit 1)
	uv run python scripts/new_domain.py $(DOMAIN) --service $(SERVICE) $(if $(ENTITY),--entity $(ENTITY))

lint: ## Run the Ruff linter
	uv run ruff check src/ tests/

fmt: ## Auto-format with Ruff
	uv run ruff format src/ tests/

check: fmt lint ## Format, lint, then mypy type-check
	uv run mypy src/

test: ## Run the whole test suite
	uv run pytest -v

test-unit: ## Run unit tests only
	uv run pytest tests/global/unit/ tests/domains/*/unit/ -v

test-integration: ## Run integration tests only
	uv run pytest tests/global/integration/ tests/domains/*/integration/ -v

test-fuzz: ## Run fuzz (Hypothesis) tests only
	uv run pytest tests/domains/*/fuzz/ -v

coverage: ## Run tests with coverage (fails under 80 %)
	uv run pytest --cov=src --cov-report=html --cov-fail-under=80

openapi: ## Generate the OpenAPI schema
	uv run python scripts/generate_openapi.py

docker-build: ## Build a service image locally (SERVICE=api)
	docker build \
		--file src/services/$(SERVICE)/Dockerfile \
		--tag blitz-$(SERVICE):local \
		--cache-from type=registry,ref=$(IMAGE):buildcache \
		.

docker-push: ## Build and push a service image to GHCR (SERVICE=api)
	docker build \
		--file src/services/$(SERVICE)/Dockerfile \
		--tag $(IMAGE):latest \
		--tag $(IMAGE):sha-$(shell git rev-parse --short HEAD) \
		--cache-from type=registry,ref=$(IMAGE):buildcache \
		--cache-to   type=registry,ref=$(IMAGE):buildcache,mode=max \
		--push \
		.

docker-run: ## Run a locally built service image (SERVICE=api, PORT=8000)
	docker run --rm -p $(PORT):8000 \
		--env-file .env \
		blitz-$(SERVICE):local

clean: ## Remove caches and build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .venv dist build htmlcov coverage.xml .coverage
