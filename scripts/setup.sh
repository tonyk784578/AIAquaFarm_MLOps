#!/usr/bin/env bash
# AIAquafarm initial project setup script
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { echo -e "${GREEN}[INFO]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }
section() { echo -e "\n${BOLD}==> $*${RESET}"; }

section "AIAquafarm Setup"
echo "This script will set up the AIAquafarm development environment."

# ── Check prerequisites ────────────────────────────────────────
section "Checking prerequisites"

command -v docker   >/dev/null || error "Docker is not installed."
command -v docker compose version >/dev/null 2>&1 || \
  command -v docker-compose >/dev/null || error "Docker Compose is not installed."
command -v make    >/dev/null || warn "Make is not installed. Run docker commands directly."

info "Docker: $(docker --version)"
info "Docker Compose: $(docker compose version 2>/dev/null || docker-compose --version)"

# ── Environment file ───────────────────────────────────────────
section "Setting up environment file"

if [ ! -f .env ]; then
    cp .env.example .env
    info ".env created from .env.example"
    warn "Please edit .env and set SECRET_KEY and ANTHROPIC_API_KEY before starting."
else
    info ".env already exists — skipping"
fi

# ── Build images ───────────────────────────────────────────────
section "Building Docker images"
docker compose build

# ── Start infrastructure ───────────────────────────────────────
section "Starting infrastructure services"
docker compose up -d postgres redis mlflow

info "Waiting for PostgreSQL to be ready..."
until docker compose exec -T postgres pg_isready -U aquafarm -d aquafarm >/dev/null 2>&1; do
    sleep 2
done
info "PostgreSQL is ready."

# ── Run migrations ─────────────────────────────────────────────
section "Running database migrations"
docker compose up -d backend
sleep 5  # Wait for backend to start

docker compose exec -T backend alembic upgrade head || \
    warn "Migration failed — tables may be created by init_db() on first start"

# ── Start remaining services ───────────────────────────────────
section "Starting all services"
docker compose up -d

info "Waiting for all services to be healthy..."
sleep 10

# ── Health check ───────────────────────────────────────────────
section "Health check"
python3 scripts/health_check.py || warn "Some services may not be fully ready yet"

echo ""
echo -e "${GREEN}${BOLD}Setup complete!${RESET}"
echo ""
echo "  Dashboard:    http://localhost"
echo "  API Docs:     http://localhost:8000/api/docs"
echo "  MLflow:       http://localhost:5000"
echo ""
echo "  Run 'make logs' to view service logs"
echo "  Run 'make seed' to load test data"
