# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

This release covers the platform's transition from *prototype with libraries*
to *production-runtime with observability + resilience*. Most additions are
listed below grouped by the area they touch.

### Added

#### MLOps runtime
- `mlops_scheduler` long-running container — runs AutoML (60 min) + Drift
  (15 min) cycles, emits per-cycle audit events
- `mlops_api` FastAPI service on :8002 with read endpoints
  (`/registry`, `/audit`, `/drift`) and superuser-gated admin actions
  (`/retrain`, `/promote`, `/deploy`)
- JSONL audit log (`/data/audit/automl.jsonl`) with 8 MiB auto-rotation
- 3-state circuit breaker + 30 s TTL response cache around all MLflow calls
- Backend proxy router `/api/v1/mlops/*` (cookie → service-key bridge)
- K8s manifests for both new services + nightly Postgres backup CronJob

#### Agent runtime
- Redis-backed `StateStore` for cycle + per-tank optimization history
- Redis pub/sub `EventBus` (channel `agents:events`) + SSE endpoint
  `/events/stream`
- `AgentHTTPClient` + `LLMClient` with tenacity retry policies
  (4× backoff on rate limits, 3× on 5xx/connect)
- `X-Service-Key` auth on `/run` + `/optimize` (no more open trigger)
- Multi-tank scheduler — iterates over `DEFAULT_TANK_IDS` instead of `ALL`
- `/history`, `/history/optimization` endpoints

#### Frontend
- MLOps page: live MLflow registry table + drift PSI cards + audit timeline
  + superuser action buttons (retrain / promote / deploy)
- Agents page: live SSE event stream + cycle history timeline
- `useEventSource` hook — auto-reconnect with exponential backoff
- Global `ErrorBoundary` (outer + per-route) — no more white screens
- `openapi-typescript` codegen pipeline (`make codegen`)

#### Observability
- Prometheus `/metrics` exposed on backend, agents, mlops_api via
  `prometheus-fastapi-instrumentator`
- OpenTelemetry OTLP tracing — auto-instruments FastAPI, httpx, SQLAlchemy,
  redis; activates only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set
- Optional compose stack (`docker-compose.observability.yml`) with
  Prometheus + Grafana + OTel Collector

#### Security hardening
- Rate limits beyond `/auth/login`: `/control/*` (60/min, exempt internal
  service callers), `/alerts/` (30/min), `/mlops/{retrain,promote,deploy}`
  (10/min, no exemption)
- Request body size cap — 1 MiB middleware on every FastAPI service
- Defence-in-depth headers (HSTS / CSP / X-Frame-Options / Referrer-Policy /
  Permissions-Policy) on both Nginx and FastAPI
- `MLOPS_CORS_ORIGINS` — direct browser access to the MLOps API is blocked
  by default
- Sealed-secrets and SOPS workflows documented in
  `infra/k8s/secrets/README.md`; `.sops.yaml` shipped as policy
- gitleaks CI job + `.gitleaks.toml`

#### Testing + dev tooling
- Vitest + React Testing Library setup; 30+ frontend tests covering
  formatters, SSE hook, WebSocket hook, ErrorBoundary
- Playwright E2E config + smoke scenarios (auth flow + MLOps page)
- New backend tests for rate-limit helpers + security middleware (size cap,
  header injection)
- New MLOps tests for circuit breaker + response cache
- CI jobs: `secret-scan`, `test-frontend`, `test-mlops`, `test-agents`
  alongside existing `lint`, `test-backend`, `docker-build`
- k6 load scripts (`load/dashboard.k6.js`, `monitoring-ws.k6.js`,
  `agents-sse.k6.js`)

#### Documentation + collaboration
- [`docs/runbook.md`](docs/runbook.md) — 9 incident scenarios + 2 routine
  procedures (emergency feeder stop, service-key rotation)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — onboarding, branch/commit
  conventions, CI job table, testing checklist
- `.github/pull_request_template.md` with risk/rollout checkboxes

### Changed
- Agent service version bumped 0.1.0 → 0.2.0 to reflect the runtime overhaul
- Backend `create_app` now wires the size-limit + security-header middlewares
  in addition to the existing CORS + rate-limit chain
- `docker-compose.yml` defines `x-backend-env` block carrying observability
  settings so all FastAPI services pick them up uniformly
- Nginx `client_max_body_size` lowered from 50M → 2M (model checkpoints go
  straight to S3, never through nginx)

### Security
- Internal service traffic identification (`X-Service-Key`) reused as
  rate-limit exemption signal — single secret governs both auth and
  burst-rate policy
- Tightened MLOps API CORS — was `allow_origins=["*"]`, now explicit env
  opt-in
- Added explicit `.gitignore` patterns for `*.key`, `*.pem`, decrypted
  secrets directories

### Notes for upgraders
- Run `make codegen` after pulling — frontend types now derive from
  `/openapi.json`.
- `make backup` is available locally; production should adopt the K8s
  CronJob at `infra/k8s/postgres/backup-cronjob.yaml`.
- Set `OTEL_EXPORTER_OTLP_ENDPOINT` to enable tracing in production.
  `/metrics` is on unconditionally — point Prometheus at the three FastAPI
  service ports.
- Move from the plaintext `infra/k8s/secrets.yaml` template to either
  sealed-secrets or SOPS before applying to staging/prod.

---

## [0.1.0] - 2026-04-01

Initial public release with the foundational platform — see git history for
the full Phase 1 → Phase 5 implementation timeline.

[Unreleased]: https://github.com/your-org/aiaquafarm/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/aiaquafarm/releases/tag/v0.1.0
