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

# MLOps / agents tests run in their own pytest suites (also run by CI)
docker compose exec mlops_api pytest /app/mlops/tests/ -v
docker compose exec agents    pytest /src/agents/tests/ -v

# Frontend tests (Vitest + Playwright) — run on the host, not in a container
cd frontend && npm install && npm run type-check && npm test
npm run e2e:install && npm run e2e   # Playwright; needs the stack `make up` first

# Logs
make logs-backend
make logs-agents

# DB migrations + backups
make migrate                             # apply head
make makemigration MSG="add user table"  # generate new migration
make backup                              # pg_dump → ./backups/; ARGS=--upload pushes to S3

# Frontend type sync — regenerate src/types/api.d.ts from /openapi.json
make codegen

# Optional observability stack (Prometheus + Grafana + OTel Collector)
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
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
| `agents` | 8001 | LangGraph agent FastAPI server (+ SSE `/events/stream`) |
| `mlops_scheduler` | — | Long-running AutoML + drift cycles, audit log writer |
| `mlops_api` | 8002 | FastAPI for MLflow registry / audit / drift / admin actions |
| `frontend` | 80 | React dashboard (via Nginx) |
| `postgres` | 5432 | PostgreSQL 15 + TimescaleDB |
| `redis` | 6379 | Pub/sub control bus + WS fan-out + agent state/events |
| `mlflow` | 5000 | MLflow tracking server |
| `nginx` | 80 | Reverse proxy (prod) |

Optional observability stack — start with
`docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d`:

- `prometheus` (9090) — scrapes `/metrics` from backend/agents/mlops_api
- `grafana` (3001) — dashboard frontend (admin/admin by default)
- `otel-collector` (4317/4318) — receives OTLP traces; activates when `OTEL_EXPORTER_OTLP_ENDPOINT` is set

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
    every node also PUBLISHes to Redis agents:events for the SSE stream

Browser → Nginx → backend /api/v1/mlops/* → (X-Service-Key injected) → mlops_api:8002
    mlops_api wraps MLflow calls in a circuit breaker + 30s response cache;
    on outage it serves the last cached snapshot so the dashboard stays
    populated. Admin POST endpoints (retrain/promote/deploy) are gated by
    require_superuser on the backend before the proxy hop.

mlops_scheduler (long-running, no HTTP)
    AutoML cycle (every MLOPS_AUTOML_INTERVAL_MIN, default 60)
    Drift  cycle (every MLOPS_DRIFT_INTERVAL_MIN,  default 15)
        → writes JSONL events to /data/audit/automl.jsonl
        → registry transitions performed via MLflow client
```

### Backend (`backend/`)

- **Entry point**: `app/main.py` — FastAPI `create_app()` with a lifespan that inits DB, Redis, all three inference engines, `SensorPublisher`, and registers the slowapi rate-limiter.
- **Settings**: `app/config.py` (`get_settings()`) — single `Settings` object loaded from `.env` via pydantic-settings; cached with `@lru_cache`.
- **DB session**: `app/db/session.py` — async SQLAlchemy engine; `get_db()` yields `AsyncSession`. TimescaleDB hypertables are created by `infra/postgres/init.sql` at container boot, not by Alembic.
- **Redis**: `app/db/redis.py` — module-level singleton `_redis`; `init_redis()` called in lifespan, `get_redis()` is a FastAPI dependency.
- **Auth**: `app/core/security.py` (JWT via python-jose + passlib/bcrypt). Access and refresh tokens use separate HMAC secrets (`secret_key` / `jwt_refresh_secret_key`). Both carry `iat` (issued-at) and `type` claims. `get_current_user` in `app/api/v1/auth.py` accepts authentication via **httpOnly cookie** (`aq_access`) **or** Bearer token — whichever is present.
- **Rate limiting**: `app/core/limiter.py` — shared slowapi `Limiter` (key: client IP). Limits per route: `POST /auth/login` 10/min, `/control/*` 60/min, `/alerts/` 30/min (both exempt internal services via `is_internal_service`), `/mlops/{retrain,promote,deploy}` 10/min (no exemption — superuser only). The `is_internal_service(request)` helper returns True iff `X-Service-Key` matches `INTERNAL_API_KEY`, so the agent container's single IP never saturates the bucket.
- **HTTP hardening** (`app/core/security_middleware.py`): `RequestSizeLimitMiddleware` rejects bodies > `MAX_REQUEST_BYTES` (1 MiB default) via Content-Length fast path + streaming fallback (413). `SecurityHeadersMiddleware` injects `X-Content-Type-Options`, `X-Frame-Options DENY`, `Referrer-Policy`, `Permissions-Policy` to every response. Both registered in `create_app()`.
- **Observability** (`app/observability.py`): `setup_observability(app, service_name)` attaches `/metrics` via `prometheus-fastapi-instrumentator` and, when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, configures OpenTelemetry tracing (auto-instruments FastAPI, httpx, SQLAlchemy, redis). Both are best-effort — missing optional deps degrade silently.
- **MLOps proxy** (`app/api/v1/mlops.py`): browser-cookie-authenticated proxy to `mlops_api:8002`. Read routes (`/registry`, `/audit`, `/drift`) forward as-is; write routes (`/retrain`, `/promote`, `/deploy`) are wrapped in `Depends(require_superuser)` and inject `X-Service-Key` automatically so the browser never sees the internal key.
- **Authorization layers** (`app/api/router.py`):
  - `get_current_user` — browser-only routes: dashboard, settings, WebSocket
  - `require_auth_or_service` (`app/api/deps.py`) — routes also used by agents: monitoring, control, alerts, AI model endpoints. Accepts JWT **or** `X-Service-Key: <internal_api_key>` header.
  - `require_superuser` — admin routes only.
- **Inference engines**: each AI module has a service singleton (`app/services/{water_quality,growth,feeding}_service.py`) loaded in lifespan onto `app.state`. Endpoints access them via `request.app.state.<engine>`.
- **Real-time pipeline**: `app/services/sensor_publisher.py` runs an asyncio loop publishing JSON WSMessages to `wq:{tank_id}`. `app/api/v1/ws_monitoring.py` subscribes to both `wq:{tank_id}` and `events:alerts`, forwarding to connected WebSocket clients. The listener and ping tasks are waited with `asyncio.FIRST_COMPLETED` so a normally-returning listener (e.g. Redis disconnect caught internally) immediately cancels the ping task.
- **Dashboard caching**: `GET /api/v1/dashboard/summary` injects a Redis client and passes it to `MonitoringService`, enabling the 5 s TTL cache in `_cache_get`/`_cache_set`. Without the injected client the cache is silently skipped (no new connections are created).

### Agents (`agents/`)

Separate FastAPI app (`agents/main.py`, port 8001, version 0.2.0) with two LangGraph graphs and a runtime layer.

- **Management graph** (`management_agent/graph.py`): `collect_data → analyse_situation → [execute_commands] → generate_report`. Claude (`claude-sonnet-4-6`) uses tool-use to call `decide_control_action`. Falls back to `RuleBasedOptimizer` if the LLM call fails.
- **Optimization subgraph** (`optimization_agent/graph.py`): `gather_module_outputs → generate_candidates → simulate_in_twin → select_optimal`. Claude proposes candidate actions; `twin_sim.py` validates them with a nitrification ODE; the highest-scored action is returned. The management graph calls this as a subgraph in `analyse_situation`.
- **Config**: `agents/config.py` (`get_agent_settings()`) — reads `ANTHROPIC_API_KEY`, `BACKEND_URL`, `REDIS_URL`, `BACKEND_API_KEY`, `DEFAULT_TANK_IDS`, `CYCLE_INTERVAL_SECONDS`, `HISTORY_SIZE`, `LLM_TIMEOUT_SECONDS` from `.env`.
- **Runtime layer** (`agents/runtime/`):
  - `http.py` — `AgentHTTPClient` async context manager wrapping httpx with `X-Service-Key` headers, timeouts, and the `@retry_http` decorator (3 attempts, exponential 0.5→4 s).
  - `llm.py` — `LLMClient` wrapping `anthropic.AsyncAnthropic` with `@retry_llm` (4 attempts, random exponential 1→20 s, retries rate-limit + server errors).
  - `retry.py` — tenacity decorators with structlog logging on every attempt.
  - `state_store.py` — Redis-backed `StateStore` for last cycle, per-tank optimization, and bounded history lists (`agents:last:management`, `agents:last:optimization:{tank}`, `agents:history:*`).
  - `event_bus.py` — Redis pub/sub on channel `agents:events`. `EventBus.timed_node(name, tank_id)` async context manager emits `node_started`/`node_completed` events with `duration_ms`.
  - `auth.py` — `require_service_key` FastAPI dependency. Applied to `POST /run` + `POST /optimize`.
  - `security.py` — same `RequestSizeLimitMiddleware` + `SecurityHeadersMiddleware` as the backend (mirror of `backend/app/core/security_middleware.py`; the three services are packaged separately so the code is duplicated by design).
- **Scheduler**: `main.py::_scheduler()` iterates over `settings.default_tank_ids` every `cycle_interval_seconds` (default 300) and runs the management graph per tank. Redis disconnections fall back to `_InMemoryStateStore` (no persistence, no history).
- **SSE endpoint**: `GET /events/stream` (sse-starlette) tails the `agents:events` channel and forwards each event as `event: agent\ndata: <json>`, with `event: ping` keepalives. The frontend's `useEventSource` hook consumes it.
- **History endpoints**: `GET /history` and `GET /history/optimization` (default n=20, max 200) read from `StateStore`.
- **Service auth — outbound**: all httpx calls from agents pass `X-Service-Key: {backend_api_key}` via `AgentHTTPClient` (no per-file helper needed anymore).
- **Service auth — inbound**: `/run` and `/optimize` require `X-Service-Key`; read endpoints (`/status`, `/history`, `/events/stream`, `/health`) are open within the cluster network.

### AI Modules (`ai_modules/`)

Three self-contained packages with no FastAPI dependency:

| Package | Model | Key classes |
|---------|-------|-------------|
| `water_quality/` | LSTM / Transformer | `WaterQualityPredictionModel`, `VirtualSensor`, `FeatureScaler`, `WindowBuilder` |
| `growth/` | YOLOv8 | `FishDetectionModel`, `SizeEstimator`, `FishCounter` |
| `feeding/` | ResNet18 regression | `FeedingActivityModel`, `ActivityAnalyzer`, `FeedOptimizer` |

Each module has a `schemas.py` (Pydantic I/O), a `model.py` (PyTorch wrapper with `.load()`, `.save_checkpoint()`, `.pytorch_model()`, `.is_loaded` flag), and a `mlflow_loader.py`. Models degrade gracefully when checkpoints are not found — they return mock/default values rather than raising.

### MLOps (`mlops/`)

The MLOps package contains both **libraries** (pure-Python, importable from training scripts and notebooks) and **two runtime services** that share the same code.

#### Libraries

- **Training scripts**: `mlops/training/train_{water,feeding,growth}.py` — standalone CLI scripts, each runs `mlflow.start_run()`, trains, logs metrics, optionally calls `mlflow.register_model()`.
- **Evaluation**: `mlops/evaluation/evaluator.py` — `QualityGate` defines per-model metric thresholds; `ModelEvaluator.evaluate_and_maybe_promote()` compares a candidate run against the gate and current Production model, then promotes if it wins.
- **Drift detection**: `mlops/evaluation/drift_detector.py` — `DriftDetector` computes PSI + KL-divergence between reference and current distributions. `should_retrain` flips at PSI ≥ 0.20.
- **AutoML**: `mlops/training/automl.py` — `AutoMLPipeline.check_and_retrain()` counts new samples from the data lake AND inspects drift, then triggers retraining when either threshold is met, then calls the evaluator.
- **Registry**: `mlops/registry/mlflow_registry.py` — `ModelRegistry.validate_and_register()` runs a signature forward-pass check before calling `mlflow.register_model()`. Also exposes A/B testing helpers (promote/graduate/rollback canary).
- **Edge deployment**: `mlops/deployment/edge_deployer.py` — downloads Production checkpoint → exports ONNX → SCP to edge → smoke-tests → rolls back on failure.
- **Data lake**: `mlops/data_lake/storage.py` — boto3 S3 client (`DataLakeStorage`); partition scheme is `raw/{camera|sensor|labelled}/{tank_id}/{YYYY-MM-DD}/`.

Registered model names: `FishDetection`, `FeedingActivityClassifier`, `WaterQualityPredictor`.

#### Runtime services

- **Orchestrator** (`mlops/orchestrator/`):
  - `audit_log.py` — `AuditLog` JSONL append-only writer with `fcntl.flock` + `fsync`. Auto-rotates at 8 MiB by dropping the oldest 25 %. Event kinds: `automl`, `drift`, `promotion`, `rollback`, `deployment`, `training`, `error`.
  - `scheduler.py` — `OrchestratorScheduler` runs `run_automl_cycle()` every `MLOPS_AUTOML_INTERVAL_MIN` (60) and `run_drift_cycle()` every `MLOPS_DRIFT_INTERVAL_MIN` (15) via the `schedule` library. Each run writes 1 pipeline-level event + 1 per-model event + 1 `promotion` event per promoted model. The same module is invoked as `python -m mlops scheduler` (the default container CMD).
- **API** (`mlops/api/`):
  - `server.py` — FastAPI app on `:8002`. Read endpoints: `GET /health`, `/registry`, `/audit?n=&kind=&model=`, `/drift`. Admin endpoints (require `X-Service-Key`): `POST /retrain`, `/promote`, `/deploy`. `app.state.mlflow_breaker` + `app.state.mlflow_cache` provide circuit-breaker resilience.
  - `resilience.py` — pure-stdlib `CircuitBreaker` (3-state: CLOSED/OPEN/HALF_OPEN, `failure_threshold=5`, `recovery_seconds=30`) + `ResponseCache` (30 s TTL, unbounded `get_stale()` fallback). `call_with_fallback()` is the helper used by endpoints. MLflow client calls are sync, so endpoints wrap them in `asyncio.to_thread`.
  - `security.py` — mirror of the agents/backend hardening middlewares.
- **Settings**: `mlops/config.py` (`get_settings()`) — Pydantic settings cached singleton. Notable fields: `mlflow_tracking_uri`, `audit_log_path`, `automl_interval_minutes`, `drift_only_interval_minutes`, `dry_run`, `internal_api_key`, `api_port`, `cors_origins` (default empty → blocks direct browser access; the backend proxy is the only public path).
- **Dispatcher**: `python -m mlops <scheduler|api|collector|automl|deploy>` — single entry point for the same image used by both services. K8s manifests:
  - `infra/k8s/mlops/scheduler-deployment.yaml` — Deployment (replicas=1, strategy=Recreate, mounts the audit-log PVC).
  - `infra/k8s/mlops/api-deployment.yaml` — Deployment + ClusterIP Service (`mlops-api:8002`).
  - `infra/k8s/mlops/cronjob.yaml` — safety-net 6 h CronJob.
  - `infra/k8s/postgres/backup-cronjob.yaml` — nightly `pg_dump` → S3.

### Frontend (`frontend/`)

React 18 + TypeScript + Vite + TailwindCSS. State: React Query (`@tanstack/react-query`) for server state, Zustand (`src/stores/themeStore.ts`) for client state, `AuthContext` for user profile.

- **Auth flow**: tokens are stored in **httpOnly cookies** set by the server on login; JavaScript never reads them. `AuthContext` tracks only the user profile object (`UserProfile`). On 401, the interceptor calls `POST /v1/auth/refresh` with no body — the `aq_refresh` cookie is sent automatically.
- **API client**: `src/services/api.ts` — all functions call `apiClient` (axios instance with `baseURL = VITE_API_BASE_URL/api`, `withCredentials: true`). Endpoints are prefixed `/v1/…`.
- **Agent client**: `src/services/api.ts` — `agentClient` with `baseURL = VITE_AGENT_BASE_URL || '/agents'`. Agent API paths are relative (`health`, `run`, `optimize`).
- **WebSocket**: `src/hooks/useWebSocket.ts` — connects to `ws://{host}/api/v1/ws/monitoring/{tankId}`, linear backoff capped at 4× `reconnectInterval` (default 3 s), max attempts default 5. Cookie auth applies to the upgrade handshake.
- **SSE**: `src/hooks/useEventSource.ts` — consumes `/agents/events/stream`. Native `EventSource` reconnect plus explicit exponential backoff (1 s → 30 s capped, optional `maxReconnectAttempts`). Parses the `agent` event channel; ignores `ping` keepalives. Drops malformed JSON silently.
- **Error boundary**: `src/components/ErrorBoundary.tsx` — wraps both `<App>` (outermost) and `<AppLayout>` Routes (per-route boundary). Uses inline styles so the fallback renders even if Tailwind / CSS vars fail. Exposes a `reset` callback.
- **MLOps panels** (`src/components/MLOps/MLOpsPage.tsx`): `RegistryPanel` (live MLflow versions + superuser action buttons), `DriftPanel` (PSI cards with feature top-5), `AuditPanel` (50 events, kind filter). All call backend `/api/v1/mlops/*` via cookie auth.
- **Agents panels** (`src/components/Agents/AgentsPage.tsx`): `AgentEventStream` (SSE 50-event ring), `AgentHistoryTimeline` (polls `/history`), in addition to the original `AgentLiveStatus` and `AgentGraphVisualization`.
- **Shared formatters**: `src/utils/format.ts` — `summariseAudit`, `eventSummary` (extracted from the page components so they're unit-tested via Vitest).
- **Testing**: Vitest + React Testing Library + jsdom in `vite.config.ts::test`. Tests live next to the code in `src/**/*.test.{ts,tsx}`. The setup file at `src/test/setup.ts` installs a `MockEventSource` and `MockWebSocket` polyfill so the SSE and WS hooks are testable without a browser. Playwright E2E in `frontend/e2e/` runs against a live `make up` stack.
- **Dev proxy** (`vite.config.ts`): `/api` → `localhost:8000`, `/agents` → `localhost:8001` (with path rewrite).
- **Mock mode**: set `VITE_USE_MOCK=true` in `frontend/.env.local`. `src/mocks/setup.ts` installs axios custom adapters that intercept all `apiClient` and `agentClient` requests; `src/mocks/data.ts` provides deterministic seed-based data. No network calls are made; the full UI including login works offline.
- **Dark mode**: `src/stores/themeStore.ts` (Zustand persist, key `aq-theme`). `main.tsx` applies the saved class before first render to prevent flash. Styles use CSS variables defined in `global.css` (`:root` / `.dark`).
- **Key pages**: `/dashboard` (`Dashboard/index.tsx` — `SystemFlowPanel` 5-stage data-flow pipeline + KPI row + WaterQuality + FishGrowth + Feeding + Alert panels), `/water-quality` (WaterQualityPage — per-tank detail + 24h Recharts history), `/control` (ControlPanel), `/growth` (GrowthPage), `/feeding` (FeedingPage), `/alerts` (AlertsPage), `/agents` (`Agents/AgentsPage.tsx` — LangGraph runtime: `AgentLiveStatus` + `AgentEventStream` (SSE) + `AgentHistoryTimeline` + `AgentGraphVisualization` 3-lane SCADA topology with live sensor/actuator readings, optimization subgraph, cycle trace), `/mlops` (`MLOps/MLOpsPage.tsx` — live MLflow `RegistryPanel` + `DriftPanel` + `AuditPanel` + superuser action buttons, plus the static lifecycle / PSI / AutoML reference cards), `/settings` (SettingsPage with model status cards + threshold editor), `/login` (LoginPage).
- **Sidebar grouping** (`Layout/Sidebar.tsx`): 5 semantic sections — `개요` (Dashboard) · `실시간 운영` (수질·제어·알림) · `AI 분석` (성장·급이) · `AI 운영` (AI 에이전트·MLOps 모델) · `관리` (설정). Order mirrors the dashboard's SystemFlowPanel pipeline stages.

### Digital Twin (`agents/optimization_agent/twin_sim.py`)

Physics-based water quality simulator used exclusively by the optimization agent. Implements the same nitrification ODE as `scripts/generate_wq_test_data.py` (`k_nit`, `k_nox` Arrhenius equations). `evaluate_candidates()` accepts current sensor readings as initial conditions and returns a `SimulationResult` per candidate action over a configurable horizon.

---

## Key Conventions

- **Structured logging**: all Python code uses `structlog.get_logger()`. Log in `key=value` style, not f-strings: `logger.info("event_name", tank_id=tid, value=v)`.
- **Graceful AI degradation**: every AI model check must handle the unloaded state. Check `engine.is_ready` before inference; return sensible defaults, never raise in the request path.
- **Redis channel naming**: `wq:{tank_id}` for sensor data, `cmd:{tank_id}:{device}` for control commands, `events:alerts` for alert broadcast, `agents:events` for live agent node/decision/command events (consumed by the SSE endpoint). Device types: `feeder`, `pump`, `aeration`, `exchange`.
- **tank_id format**: `^[A-Z0-9][A-Z0-9_\-]*$` (e.g. `TANK-01`). Validated at the API boundary with `Field(pattern=...)` and `Path(pattern=...)`. The WebSocket endpoint additionally validates at runtime with a compiled regex (`_TANK_ID_RE`) and closes the connection with code 1008 on mismatch. Do not pass free-form strings as tank identifiers.
- **Auth — browser clients**: use the httpOnly `aq_access` cookie (path `/`) set by `POST /auth/login`. The `aq_refresh` cookie (path `/api/v1/auth`) is used only by `POST /auth/refresh`. No token storage in JS.
- **Auth — internal services (agents)**: send `X-Service-Key: <INTERNAL_API_KEY>` header. The backend `require_auth_or_service` dependency accepts this as an alternative to JWT. Set `INTERNAL_API_KEY` / `BACKEND_API_KEY` to the same random secret in `.env`.
- **Registration**: `POST /auth/register` returns 403 by default. Set `REGISTRATION_OPEN=true` to enable for initial superuser bootstrap, then disable.
- **Separate JWT secrets**: `SECRET_KEY` signs access tokens; `JWT_REFRESH_SECRET_KEY` signs refresh tokens. Use different random values in production.
- **MLflow model lifecycle**: `None → Staging → Production → Archived`. Only `ModelEvaluator` should call `transition_model_version_stage`; do not promote directly from training scripts.
- **Four Python roots**: `backend/` (pip-installable as `aquafarm-backend`), `agents/` (as `aquafarm-agents`), `ai_modules/` (as `aquafarm-ai`), `mlops/` (as `aquafarm-mlops`). Each has its own `pyproject.toml`. Do not import across roots at module level — services communicate via HTTP and shared infrastructure (Redis, MLflow, Postgres). Code that legitimately needs to exist in multiple services (e.g. `security.py` middleware) is duplicated by design.
- **Parameterized SQL only**: never interpolate user-supplied values into `text()` queries. Use named bind parameters (`:param`) for all dynamic values, including interval expressions (use `make_interval(mins => :bucket_minutes)` not `f"'{n} minutes'"`).
- **Rate-limit exemption for internal services**: when adding a slowapi-decorated endpoint that legitimately receives calls from the agents container, decorate with `exempt_when=is_internal_service` (from `app.core.limiter`). Otherwise the single-IP agent container saturates the bucket within seconds.
- **MLflow access from FastAPI**: never call the MLflow client directly from a request handler. Wrap it in `asyncio.to_thread` + the circuit breaker (`app.state.mlflow_breaker`) so an MLflow outage doesn't propagate as 500s. Pattern in `mlops/api/server.py::list_registry`.
- **Audit log writes**: any new MLOps automation must emit an `AuditEvent` via `AuditLog.log(kind, model, data)` — this is how the dashboard and `/api/v1/mlops/audit` surface the activity. Available kinds are typed in `mlops/orchestrator/audit_log.py::EventKind`.
- **Agent SSE events**: new agent nodes should wrap themselves in `async with bus.timed_node("node_name", tank_id=...)` so `node_started` and `node_completed` events (with `duration_ms`) reach the frontend automatically. For domain events (decisions, command results), call `bus.publish(kind, tank_id, data)` directly.
- **Observability instrumentation**: don't add ad-hoc Prometheus counters. The `/metrics` endpoint is wired in `observability.py` per service; structlog + the OTel auto-instrumentors (FastAPI, httpx, SQLAlchemy, redis) cover the cross-cutting telemetry. If you need a domain metric, prefer extending a counter in the relevant service module and let `prometheus_fastapi_instrumentator` pick it up.
- **Security headers + body cap**: every new FastAPI service must register `RequestSizeLimitMiddleware` + `SecurityHeadersMiddleware`. The backend version is in `app/core/security_middleware.py`; the agents version in `agents/runtime/security.py`; the mlops_api version in `mlops/api/security.py`. Keep the three in sync.
- **Secret management**: never commit plaintext secrets. The `infra/k8s/secrets.yaml` template is dev-only. Production uses sealed-secrets or SOPS — see [`infra/k8s/secrets/README.md`](infra/k8s/secrets/README.md). `gitleaks` runs in CI; check `.gitleaks.toml` for the allowlist of example values.
- **Frontend tests**: pure helpers live in `src/utils/` so they're testable without React. Hooks that wrap browser APIs (EventSource, WebSocket) rely on the polyfills installed in `src/test/setup.ts`. The Vitest config has `globals: true`, but prefer explicit `import { describe, expect, it } from 'vitest'` for clarity.
- **Markdown linting**: project markdown is checked by markdownlint (MD060 in particular). Wide / variable-width tables (especially with mixed-Korean content) often trigger alignment warnings — prefer a bullet list for those.
