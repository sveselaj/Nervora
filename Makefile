.DEFAULT_GOAL := help
PY ?= python3

.PHONY: help install dev up down logs test lint fmt seed demo token clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install the project + dev dependencies (editable)
	$(PY) -m pip install -e ".[dev]"

up: ## Start the full local stack (gateway, worker, postgres, otel, grafana)
	docker compose -f infra/docker-compose.yml up --build

down: ## Stop the stack and remove volumes
	docker compose -f infra/docker-compose.yml down -v

logs: ## Tail stack logs
	docker compose -f infra/docker-compose.yml logs -f

test: ## Run the pytest suite (SQLite-backed, no Postgres needed)
	$(PY) -m pytest

lint: ## Lint with ruff
	$(PY) -m ruff check packages apps tests

fmt: ## Auto-format with ruff
	$(PY) -m ruff check --fix packages apps tests

demo: ## Run the scripted demo agent flow against a running gateway
	$(PY) apps/demo-agent/agent.py demo

token: ## Mint a dev test token, e.g. make token ROLE=finance_agent
	$(PY) apps/demo-agent/agent.py token --role $(or $(ROLE),finance_agent)

clean: ## Remove caches and local artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__ *.egg-info
