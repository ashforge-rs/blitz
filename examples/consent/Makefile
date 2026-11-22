.DEFAULT_GOAL := help
.PHONY: help install verify fmt test coverage dev migrate api-key seed

PY_DIRS := consent_app/ consent_tests/ conftest.py
PORT    ?= 8000

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the example and its dev dependencies (own .venv)
	uv sync

verify: ## Check everything without changing files: format, lint, types, tests
	uv run ruff format --check $(PY_DIRS)
	uv run ruff check $(PY_DIRS)
	uv run mypy consent_app/ consent_tests/ conftest.py
	uv run pytest

fmt: ## Auto-format and fix lint
	uv run ruff format $(PY_DIRS)
	uv run ruff check --fix $(PY_DIRS)

test: ## Run the tests
	uv run pytest -v

coverage: ## Tests with coverage (fails under 90 %)
	uv run pytest --cov --cov-fail-under=90

dev: ## Run the HTTP API with hot reload (PORT=8000)
	uv run uvicorn consent_app.main:app --reload --port $(PORT)

migrate: ## Apply pending migrations (CONSENT_DATABASE_URL)
	uv run python -m consent_app.adapters.sql.migrate

api-key: ## Create an API key for a client system: make api-key CLIENT=crm
	@uv run python -m consent_app.adapters.api_keys $(CLIENT)

seed: ## Load demo purposes and consent decisions (not in production)
	uv run python -m consent_app.adapters.seed
