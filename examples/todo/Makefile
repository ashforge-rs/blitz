.DEFAULT_GOAL := help
.PHONY: help install verify fmt test coverage dev db-up db-down migrate

PY_DIRS := todo_app/ todo_tests/ conftest.py
PORT    ?= 8000

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the example and its dev dependencies (own .venv)
	uv sync

verify: ## Check everything without changing files: format, lint, types, tests
	uv run ruff format --check $(PY_DIRS)
	uv run ruff check $(PY_DIRS)
	uv run mypy todo_app/ todo_tests/ conftest.py
	uv run pytest

fmt: ## Auto-format and fix lint
	uv run ruff format $(PY_DIRS)
	uv run ruff check --fix $(PY_DIRS)

test: ## Run the tests
	uv run pytest -v

coverage: ## Tests with coverage (fails under 90 %)
	uv run pytest --cov --cov-fail-under=90

dev: ## Run the HTTP app with hot reload (PORT=8000)
	uv run uvicorn todo_app.main:app --reload --port $(PORT)

db-up: ## Start Postgres (docker compose) and wait until it is healthy
	docker compose up -d --wait

db-down: ## Stop Postgres (data is kept in a volume)
	docker compose down

migrate: ## Apply pending migrations for every context (TODO_DATABASE_URL)
	uv run todo db upgrade
