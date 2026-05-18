.PHONY: help up down build rebuild logs shell migrate seed health lint test codegen backup

# Default target
help:
	@echo "AIAquafarm - Smart RAS Aquaculture Platform"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Infrastructure:"
	@echo "  up           Start all services (detached)"
	@echo "  down         Stop all services"
	@echo "  build        Build all Docker images"
	@echo "  rebuild      Rebuild images without cache"
	@echo "  restart      Restart all services"
	@echo "  logs         Tail logs for all services"
	@echo "  logs-backend Tail backend logs only"
	@echo "  logs-agents  Tail agents logs only"
	@echo "  ps           Show running containers"
	@echo ""
	@echo "Development:"
	@echo "  dev          Start in development mode"
	@echo "  shell        Open shell in backend container"
	@echo "  migrate      Run Alembic DB migrations"
	@echo "  makemigration MSG='...' Create new migration"
	@echo "  seed         Seed test data into database"
	@echo "  health       Check all service health"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint         Run ruff linter"
	@echo "  format       Run ruff formatter"
	@echo "  test         Run backend tests"
	@echo "  test-cov     Run tests with coverage"
	@echo "  codegen      Regenerate frontend TS types from backend OpenAPI"
	@echo "  backup       Dump Postgres + MLflow DB to ./backups/ (ARGS=--upload to push to S3)"
	@echo ""
	@echo "Setup:"
	@echo "  setup        Initial project setup"
	@echo "  clean        Remove containers, volumes, images"

# ── Infrastructure ────────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

rebuild:
	docker compose build --no-cache

restart:
	docker compose restart

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-agents:
	docker compose logs -f agents

logs-frontend:
	docker compose logs -f frontend

ps:
	docker compose ps

# ── Development ───────────────────────────────────────────────

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

shell:
	docker compose exec backend bash

shell-agents:
	docker compose exec agents bash

migrate:
	docker compose exec backend alembic upgrade head

makemigration:
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

seed:
	docker compose exec backend python scripts/seed_data.py

health:
	@echo "\nAIAquafarm Service Health Check\n"
	@curl -sf http://localhost:8000/health > /dev/null && echo "  ✓ Backend API      (localhost:8000)" || echo "  ✗ Backend API      (localhost:8000)"
	@curl -sf http://localhost:5000/health > /dev/null && echo "  ✓ MLflow           (localhost:5000)" || echo "  ✗ MLflow           (localhost:5000)"
	@curl -sf http://localhost/agents/health > /dev/null && echo "  ✓ Agents           (localhost/agents)" || echo "  ✗ Agents           (localhost/agents)"
	@curl -sf http://localhost/health     > /dev/null && echo "  ✓ Nginx gateway    (localhost:80)"   || echo "  ✗ Nginx gateway    (localhost:80)"
	@echo ""

# ── Code Quality ──────────────────────────────────────────────

lint:
	cd backend && ruff check app/ tests/
	cd agents && ruff check .
	cd ai_modules && ruff check .

format:
	cd backend && ruff format app/ tests/
	cd agents && ruff format .
	cd ai_modules && ruff format .

test:
	docker compose exec backend pytest tests/ -v

test-cov:
	docker compose exec backend pytest tests/ -v --cov=app --cov-report=html

# ── API type codegen ──────────────────────────────────────────
# Fetch OpenAPI spec from the running backend and regenerate
# the TypeScript type bindings consumed by the frontend.
# Requires `make up` first so http://localhost:8000/openapi.json responds.
codegen:
	@echo "Regenerating frontend/src/types/api.d.ts from backend OpenAPI"
	cd frontend && npm run codegen

# ── Database backup ───────────────────────────────────────────
# Manual on-demand pg_dump of aquafarm + aquafarm_mlflow to ./backups/.
# Use ARGS=--upload to also push to S3/MinIO (requires S3_* env vars).
# The k8s deployment runs the equivalent job nightly via
# infra/k8s/postgres/backup-cronjob.yaml.
backup:
	@scripts/backup_postgres.sh $(ARGS)

# ── Setup ─────────────────────────────────────────────────────

setup:
	@bash scripts/setup.sh

clean:
	docker compose down -v --rmi local
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
