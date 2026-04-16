.PHONY: install dev lint fmt check test coverage openapi clean

install:
	uv sync

dev:
	uv run uvicorn main:app --reload --app-dir src

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

check: fmt lint

test:
	uv run pytest -v

coverage:
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=80

openapi:
	uv run python scripts/generate_openapi.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .venv dist build htmlcov coverage.xml .coverage
