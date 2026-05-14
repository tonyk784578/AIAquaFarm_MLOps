# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Common Commands

All infrastructure commands run through Docker Compose via `make`. The stack requires Docker ≥ 24.0 and Docker Compose ≥ 2.20.

```bash
# First-time setup
cp .env.example .env        # fill in SECRET_KEY, JWT_REFRESH_SECRET_KEY,
                            # INTERNAL_API_KEY, ANTHROPIC_API_KEY
make build && make up
make migrate                # run Alembic migrations
make seed                   # insert test data

# Enable registration for the first superuser, then disable again
REGISTRATION_OPEN=true make up   # or set in .env temporarily

# Development (hot-reload for backend)
make dev

# Code quality (runs ruff on backend/, agents/, ai_modules/)
make lint
make format

# Tests (requires running containers)
make test                   # pytest inside backend container
make test-cov               # with HTML coverage report

# Single test file
docker compose exec backend pytest tests/test_api.py -v

# Logs
make logs-backend
make logs-agents

# DB migrations
make migrate                             # apply head
make makemigration MSG="add user table"  # generate new migration
```

Alembic migration files live in `backend/alembic/versions/`. The `alembic.ini` script location is relative to `backend/`.

To generate synthetic training data without a live stack:
```bash
python scripts/generate_wq_test_data.py --days 30 --tanks 3 --output data/wq.csv
python scripts/generate_feeding_test_data.py --output data/feeding_dataset/ --n-per-class 200
python scripts/generate_growth_test_data.py --output data/growth_dataset/ --n-train 800
```

---

## Architecture Overview

### Service Map (Docker Compose)

| Container | Port | Role |
|-----------|------|------|
| `backend` | 8000 | FastAPI REST + WebSocket API |
| `agents` | 8001 | LangGraph agent FastAPI server |
| `frontend` | 80 | React dashboard (via Nginx) |
| `postgres` | 5432 | PostgreSQL 15 + TimescaleDB |
| `redis` | 6379 | Pub/sub control bus + WS fan-out |
| `mlflow` | 5000 | MLflow tracking server |
| `nginx` | 80 | Reverse proxy (prod) |

### Request + Data Flow

```
Browser → Nginx → FastAPI (backend:8000)
                      │
                      ├─ REST endpoints → PostgreSQL (TimescaleDB)
                      ├─ WebSocket /api/v1/ws/monitoring/{tank_id}
                      │     └─ subscribes Redis wq:{tank_id} + events:alerts
                      └─ SensorPublisher (background asyncio task)
                            └─ ODE virtual sensor → PUBLISH wq:{tank_id}
                                    ↑ every sensor_poll_interval seconds

Browser → Nginx → agents:8001 (via /agents/ prefix)
    agents run management_graph + optimization_graph on demand
    optimization_graph → gathers AI module outputs → Claude LLM candidates
                       → twin_sim ODE evaluation → selects best action
                       → execute_commands → POST /api/v1/control/*
                           (with X-Service-Key header) → PUBLISH cmd:{tank_id}:{device} → edge
```

### Backend (`backend/`)

- **Entry point**: `app/main.py` — FastAPI `create_app()` with a lifespan that inits DB, Redis, all three inference engines, `SensorPublisher`, and registers the slowapi rate-limiter.
- **Settings**: `app/config.py` (`get_settings()`) — single `Settings` object loaded from `.env` via pydantic-settings; cached with `@lru_cache`.
- **DB session**: `app/db/session.py` — async SQLAlchemy engine; `get_db()` yields `AsyncSession`. TimescaleDB hypertables are created by `infra/postgres/init.sql` at container boot, not by Alembic.
- **Redis**: `app/db/redis.py` — module-level singleton `_redis`; `init_redis()` called in lifespan, `get_redis()` is a FastAPI dependency.
- **Auth**: `app/core/security.py` (JWT via python-jose + passlib/bcrypt). Access and refresh tokens use separate HMAC secrets (`secret_key` / `jwt_refresh_secret_key`). Both carry `iat` (issued-at) and `type` claims. `get_current_user` in `app/api/v1/auth.py` accepts authentication via **httpOnly cookie** (`aq_access`) **or** Bearer token — whichever is present.
- **Rate limiting**: `app/core/limiter.py` — shared slowapi `Limiter` (key: client IP). Applied to `POST /auth/login` (10/minute). Middleware registered in `main.py`.
- **Authorization layers** (`app/api/router.py`):
  - `get_current_user` — browser-only routes: dashboard, settings, WebSocket
  - `require_auth_or_service` (`app/api/deps.py`) — routes also used by agents: monitoring, control, alerts, AI model endpoints. Accepts JWT **or** `X-Service-Key: <internal_api_key>` header.
  - `require_superuser` — admin routes only.
- **Inference engines**: each AI module has a service singleton (`app/services/{water_quality,growth,feeding}_service.py`) loaded in lifespan onto `app.state`. Endpoints access them via `request.app.state.<engine>`.
- **Real-time pipeline**: `app/services/sensor_publisher.py` runs an asyncio loop publishing JSON WSMessages to `wq:{tank_id}`. `app/api/v1/ws_monitoring.py` subscribes to both `wq:{tank_id}` and `events:alerts`, forwarding to connected WebSocket clients. The listener and ping tasks are waited with `asyncio.FIRST_COMPLETED` so a normally-returning listener (e.g. Redis disconnect caught internally) immediately cancels the ping task.
- **Dashboard caching**: `GET /api/v1/dashboard/summary` injects a Redis client and passes it to `MonitoringService`, enabling the 5 s TTL cache in `_cache_get`/`_cache_set`. Without the injected client the cache is silently skipped (no new connections are created).

### Agents (`agents/`)

Separate FastAPI app (`agents/main.py`, port 8001) with two LangGraph graphs:

- **Management graph** (`management_agent/graph.py`): `collect_data → analyse_situation → [execute_commands] → generate_report`. Claude (`claude-sonnet-4-6`) uses tool-use to call `decide_control_action`. Falls back to `RuleBasedOptimizer` if the LLM call fails.
- **Optimization subgraph** (`optimization_agent/graph.py`): `gather_module_outputs → generate_candidates → simulate_in_twin → select_optimal`. Claude proposes candidate actions; `twin_sim.py` validates them with a nitrification ODE; the highest-scored action is returned. The management graph calls this as a subgraph in `analyse_situation`.
- **Config**: `agents/config.py` (`get_agent_settings()`) — reads `ANTHROPIC_API_KEY`, `BACKEND_URL`, `REDIS_URL`, `BACKEND_API_KEY` from `.env`.
- **Service auth**: all httpx calls from agents pass `X-Service-Key: {backend_api_key}` via `_svc_headers()` / `_service_headers()` helpers in each node/tool file.

### AI Modules (`ai_modules/`)

Three self-contained packages with no FastAPI dependency:

| Package | Model | Key classes |
|---------|-------|-------------|
| `water_quality/` | LSTM / Transformer | `WaterQualityPredictionModel`, `VirtualSensor`, `FeatureScaler`, `WindowBuilder` |
| `growth/` | YOLOv8 | `FishDetectionModel`, `SizeEstimator`, `FishCounter` |
| `feeding/` | ResNet18 regression | `FeedingActivityModel`, `ActivityAnalyzer`, `FeedOptimizer` |

Each module has a `schemas.py` (Pydantic I/O), a `model.py` (PyTorch wrapper with `.load()`, `.save_checkpoint()`, `.pytorch_model()`, `.is_loaded` flag), and a `mlflow_loader.py`. Models degrade gracefully when checkpoints are not found — they return mock/default values rather than raising.

### MLOps (`mlops/`)

- **Training scripts**: `mlops/training/train_{water,feeding,growth}.py` — standalone CLI scripts, each runs `mlflow.start_run()`, trains, logs metrics, optionally calls `mlflow.register_model()`.
- **Evaluation**: `mlops/evaluation/evaluator.py` — `QualityGate` defines per-model metric thresholds; `ModelEvaluator.evaluate_and_maybe_promote()` compares a candidate run against the gate and current Production model, then promotes if it wins.
- **AutoML**: `mlops/training/automl.py` — `AutoMLPipeline.check_and_retrain()` counts new samples from the data lake and triggers retraining when thresholds are met, then calls the evaluator.
- **Registry**: `mlops/registry/mlflow_registry.py` — `ModelRegistry.validate_and_register()` runs a signature forward-pass check before calling `mlflow.register_model()`.
- **Data lake**: `mlops/data_lake/storage.py` — boto3 S3 client (`DataLakeStorage`); partition scheme is `raw/{camera|sensor|labelled}/{tank_id}/{YYYY-MM-DD}/`.

Registered model names: `FishDetection`, `FeedingActivityClassifier`, `WaterQualityPredictor`.

### Frontend (`frontend/`)

React 18 + TypeScript + Vite + TailwindCSS. State: React Query (`@tanstack/react-query`) for server state, Zustand (`src/stores/themeStore.ts`) for client state, `AuthContext` for user profile.

- **Auth flow**: tokens are stored in **httpOnly cookies** set by the server on login; JavaScript never reads them. `AuthContext` tracks only the user profile object (`UserProfile`). On 401, the interceptor calls `POST /v1/auth/refresh` with no body — the `aq_refresh` cookie is sent automatically.
- **API client**: `src/services/api.ts` — all functions call `apiClient` (axios instance with `baseURL = VITE_API_BASE_URL/api`, `withCredentials: true`). Endpoints are prefixed `/v1/…`.
- **Agent client**: `src/services/api.ts` — `agentClient` with `baseURL = VITE_AGENT_BASE_URL || '/agents'`. Agent API paths are relative (`health`, `run`, `optimize`).
- **WebSocket**: `src/hooks/useWebSocket.ts` — connects to `ws://{host}/api/v1/ws/monitoring/{tankId}`, auto-reconnects with exponential backoff. Cookie auth applies to the upgrade handshake.
- **Dev proxy** (`vite.config.ts`): `/api` → `localhost:8000`, `/agents` → `localhost:8001` (with path rewrite).
- **Mock mode**: set `VITE_USE_MOCK=true` in `frontend/.env.local`. `src/mocks/setup.ts` installs axios custom adapters that intercept all `apiClient` and `agentClient` requests; `src/mocks/data.ts` provides deterministic seed-based data. No network calls are made; the full UI including login works offline.
- **Dark mode**: `src/stores/themeStore.ts` (Zustand persist, key `aq-theme`). `main.tsx` applies the saved class before first render to prevent flash. Styles use CSS variables defined in `global.css` (`:root` / `.dark`).
- **Key pages**: `/dashboard` (KPI row + WaterQuality + FishGrowth + Feeding + Alert panels), `/water-quality` (WaterQualityPage — per-tank detail + 24h Recharts history), `/control` (ControlPanel), `/growth` (GrowthPage), `/feeding` (FeedingPage), `/alerts` (AlertsPage), `/mlops` (MLOpsPage), `/settings` (SettingsPage with model status cards + threshold editor), `/login` (LoginPage).

### Digital Twin (`agents/optimization_agent/twin_sim.py`)

Physics-based water quality simulator used exclusively by the optimization agent. Implements the same nitrification ODE as `scripts/generate_wq_test_data.py` (`k_nit`, `k_nox` Arrhenius equations). `evaluate_candidates()` accepts current sensor readings as initial conditions and returns a `SimulationResult` per candidate action over a configurable horizon.

---

## Key Conventions

- **Structured logging**: all Python code uses `structlog.get_logger()`. Log in `key=value` style, not f-strings: `logger.info("event_name", tank_id=tid, value=v)`.
- **Graceful AI degradation**: every AI model check must handle the unloaded state. Check `engine.is_ready` before inference; return sensible defaults, never raise in the request path.
- **Redis channel naming**: `wq:{tank_id}` for sensor data, `cmd:{tank_id}:{device}` for control commands. Device types: `feeder`, `pump`, `aeration`, `exchange`.
- **tank_id format**: `^[A-Z0-9][A-Z0-9_\-]*$` (e.g. `TANK-01`). Validated at the API boundary with `Field(pattern=...)` and `Path(pattern=...)`. The WebSocket endpoint additionally validates at runtime with a compiled regex (`_TANK_ID_RE`) and closes the connection with code 1008 on mismatch. Do not pass free-form strings as tank identifiers.
- **Auth — browser clients**: use the httpOnly `aq_access` cookie (path `/`) set by `POST /auth/login`. The `aq_refresh` cookie (path `/api/v1/auth`) is used only by `POST /auth/refresh`. No token storage in JS.
- **Auth — internal services (agents)**: send `X-Service-Key: <INTERNAL_API_KEY>` header. The backend `require_auth_or_service` dependency accepts this as an alternative to JWT. Set `INTERNAL_API_KEY` / `BACKEND_API_KEY` to the same random secret in `.env`.
- **Registration**: `POST /auth/register` returns 403 by default. Set `REGISTRATION_OPEN=true` to enable for initial superuser bootstrap, then disable.
- **Separate JWT secrets**: `SECRET_KEY` signs access tokens; `JWT_REFRESH_SECRET_KEY` signs refresh tokens. Use different random values in production.
- **MLflow model lifecycle**: `None → Staging → Production → Archived`. Only `ModelEvaluator` should call `transition_model_version_stage`; do not promote directly from training scripts.
- **Three Python roots**: `backend/` (pip-installable as `aquafarm-backend`), `agents/` (as `aquafarm-agents`), `ai_modules/` (as `aquafarm-ai`). Each has its own `pyproject.toml`. Do not import across roots at module level — the agents call the backend via HTTP.
- **Parameterized SQL only**: never interpolate user-supplied values into `text()` queries. Use named bind parameters (`:param`) for all dynamic values, including interval expressions (use `make_interval(mins => :bucket_minutes)` not `f"'{n} minutes'"`).
