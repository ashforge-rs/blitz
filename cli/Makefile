.DEFAULT_GOAL := help
.PHONY: help install verify fmt test

PY_DIRS := blitz_cli/ blitz_cli_tests/

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the CLI and its dev dependencies (own .venv)
	uv sync

verify: ## Check everything without changing files: format, lint, types, tests
	uv run ruff format --check $(PY_DIRS)
	uv run ruff check $(PY_DIRS)
	uv run mypy $(PY_DIRS)
	uv run pytest

fmt: ## Auto-format and fix lint
	uv run ruff format $(PY_DIRS)
	uv run ruff check --fix $(PY_DIRS)

test: ## Run the tests
	uv run pytest -v
