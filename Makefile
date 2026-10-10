.PHONY: up down smoke test lint typecheck migrate seed help

DOCKER_COMPOSE = docker-compose -f tools/docker-compose.yml

help: ## Show this help
	@grep -E '^[a-z]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

up: ## Start local development stack (Postgres, Redis, MinIO, Langfuse, etc.)
	$(DOCKER_COMPOSE) up -d
	@echo "Waiting for services to be ready..."
	@sleep 5

down: ## Stop local development stack
	$(DOCKER_COMPOSE) down

smoke: lint typecheck ## Run smoke tests (lint + basic imports)
	@echo "✓ Smoke tests passed"

test: ## Run all tests (pytest)
	pytest packages/py_core/tests -m unit -v --cov=packages/py_core --cov-report=term-missing
	pytest ml/evals/tests -m eval -v

lint: ## Run linter (ruff check)
	ruff check packages/ services/ apps/ ml/ --fix

typecheck: ## Run type checker (mypy --strict)
	mypy packages/py_core --strict
	mypy services/ --strict

migrate: ## Run Alembic migrations
	alembic -c packages/py_core/alembic.ini upgrade head

seed: ## Seed test data
	python -m py_core.scripts.seed_test_data

.DEFAULT_GOAL := help
