.DEFAULT_GOAL := help
.PHONY: help up down reset seed todo consent dashboards

TODO_DB    := postgresql+asyncpg://examples:examples@localhost:55432/todo
CONSENT_DB := postgresql+asyncpg://examples:examples@localhost:55432/consent

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start Postgres (:55432), Prometheus (:9090) and Grafana (:3000), and wait until healthy
	docker compose up -d --wait

down: ## Stop the stack (data is kept)
	docker compose down

reset: ## Stop the stack and delete its data
	docker compose down --volumes

seed: ## Load both apps' demo data into Postgres
	cd ../todo && TODO_DATABASE_URL=$(TODO_DB) uv run todo seed
	cd ../consent && CONSENT_DATABASE_URL=$(CONSENT_DB) uv run python -m consent_app.adapters.seed

todo: ## Run the todo app on :8000 against Postgres (all interfaces: Prometheus scrapes it from Docker)
	cd ../todo && TODO_DATABASE_URL=$(TODO_DB) uv run uvicorn todo_app.main:app --host 0.0.0.0 --port 8000

consent: ## Run the consent app on :8001 against Postgres (all interfaces: Prometheus scrapes it from Docker)
	cd ../consent && CONSENT_DATABASE_URL=$(CONSENT_DB) uv run uvicorn consent_app.main:app --host 0.0.0.0 --port 8001

dashboards: ## Rebuild both dashboards' JSON from build_dashboards.py
	python3 build_dashboards.py
