.DEFAULT_GOAL := help
.PHONY: help install dev domain crud service cli cli-install doctor routes openapi-check update verify lint fmt check test test-unit test-integration test-fuzz coverage openapi docker-build docker-push docker-run clean

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
PY_DIRS := src/ tests/ scripts/
PORT    ?= 8000
BLITZ   := uv run --project cli blitz
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
	$(BLITZ) domain new $(DOMAIN) --service $(SERVICE) $(if $(ENTITY),--entity $(ENTITY))

crud: ## Wizard: an entity + its CRUD API as a new domain (ask name, fields, types)
	$(BLITZ) crud

service: ## Scaffold a service: main.py, domains.py, Dockerfile (NAME=worker)
	@test "$(origin NAME)" = "command line" || (echo "usage: make service NAME=<snake_case>" && exit 1)
	$(BLITZ) service new $(NAME)

routes: ## List every route of every service: method, path, owner, auth
	$(BLITZ) routes

openapi-check: ## Fail on breaking API changes against a git ref (REF=origin/master)
	$(BLITZ) openapi --diff $(or $(REF),origin/master) --check

update: ## Merge boilerplate changes since this project was created (blitz new)
	$(BLITZ) update

cli-install: ## Put `blitz` on PATH (editable) so shell completion works
	uv tool install --editable ./cli
	@echo "then: blitz --install-completion"

doctor: ## Check the project's rules: domain contract, registration, tests, .env.example
	$(BLITZ) doctor --import

cli: ## Run the blitz code-generator CLI (ARGS="domain list"; ARGS=--help for every command)
	$(BLITZ) $(ARGS)

verify: ## Check everything without changing files: format, lint, types, tests (+ examples/, cli/)
	uv run ruff format --check $(PY_DIRS)
	uv run ruff check $(PY_DIRS)
	uv run mypy src/
	uv run pytest
	$(MAKE) -C examples/todo verify
	$(MAKE) -C examples/consent verify
	$(MAKE) -C cli verify

lint: ## Run the Ruff linter
	uv run ruff check $(PY_DIRS)

fmt: ## Auto-format with Ruff
	uv run ruff format $(PY_DIRS)

check: fmt lint ## Format + lint (rewrites files), then mypy type-check
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
