# AIAquafarm 아키텍처 문서

## 시스템 개요

AIAquafarm은 RAS(순환여과식) 양식장을 위한 AI 통합 관리 플랫폼입니다.
6개 계층으로 구성된 멀티레이어 아키텍처를 채용합니다.

---

## 계층별 설계

### Layer 1 — 통합 대시보드 (Frontend)

**기술**: React 18 + TypeScript + Vite + TailwindCSS + React Query + Recharts + Zustand

**책임**:

- 실시간 수질/성장/급이 모니터링 UI
- 시스템 전체 데이터 흐름 가시화 (`SystemFlowPanel`)
- LangGraph 에이전트 토폴로지·사이클 트레이스 시각화 (`Agents/AgentGraphVisualization`)
- 알림 수신 및 해결 인터페이스
- 장비 원격 제어 패널
- WebSocket 기반 실시간 데이터 수신

**페이지 구성**:

| 경로 | 컴포넌트 | 설명 |
| ---- | -------- | ---- |
| `/dashboard` | `Dashboard/index.tsx` | **SystemFlowPanel** (엣지 → 백엔드 → AI → 에이전트 → 제어 5단계 파이프라인) + KPI 요약 + 수질·성장·급이·알림 패널 |
| `/water-quality` | `WaterQuality/WaterQualityPage.tsx` | 수질 지표 상세 + 24h 이력 차트 |
| `/control` | `Control/ControlPanel.tsx` | 장치 원격 제어 |
| `/growth` | `Growth/GrowthPage.tsx` | 어류 성장 분석 |
| `/feeding` | `Feeding/FeedingPage.tsx` | 급이 분석 (이벤트·활성도) |
| `/alerts` | `Alerts/AlertsPage.tsx` | 알림 목록 및 해제 |
| `/agents` | `Agents/AgentsPage.tsx` + `Agents/AgentGraphVisualization.tsx` | LangGraph 런타임 — 실시간 사이클 상태 · 3-스윔레인 SCADA 토폴로지(센서 → 그래프 노드 → 액추에이터) · optimization 서브그래프 · 사이클 트레이스 |
| `/mlops` | `MLOps/MLOpsPage.tsx` | MLOps 모델 전용 — Production 상태·생명주기·PSI 드리프트·A/B 카나리·AutoML 임계값 (에이전트 콘텐츠는 `/agents`로 분리) |
| `/settings` | `Settings/SettingsPage.tsx` | 임계값·모델 상태 설정 |

**사이드바 그룹**:

사이드바([`Layout/Sidebar.tsx`](../frontend/src/components/Layout/Sidebar.tsx))는 5개 의미 단위로 묶여 있으며 대시보드 SystemFlowPanel의 데이터 흐름 순서와 일치합니다.

| 그룹 | 메뉴 |
| ---- | ---- |
| `개요` | 대시보드 |
| `실시간 운영` | 수질 모니터링 · 제어 패널 · 알림 |
| `AI 분석` | 성장 분석 · 급이 분석 |
| `AI 운영` | AI 에이전트 · MLOps · 모델 |
| `관리` | 설정 |

**다크 모드**:

- `stores/themeStore.ts` — Zustand persist 스토어. 선택값을 localStorage(`aq-theme`)에 저장하여 새로고침 후에도 유지.
- `main.tsx` — 첫 렌더 전 `document.documentElement.classList.add('dark')` 적용으로 색상 플래시 방지.
- `global.css` — CSS 변수 기반 테마 (`--bg-base`, `--text-primary` 등). `:root`와 `.dark` 선택자로 라이트/다크 분기.

**Mock 데이터 모드**:

- `VITE_USE_MOCK=true` (`.env.local`) 설정 시 활성화.
- `mocks/setup.ts` — axios 커스텀 어댑터로 `apiClient`, `agentClient` 요청을 intercept.
- `mocks/data.ts` — 결정론적 seed 기반 목 데이터 생성기. 수질 이력·성장·급이·알림·에이전트 결과 포함.
- 실제 네트워크 요청 없음. 로그인 포함 전체 UI를 오프라인으로 시연 가능.

**인증**:

- 로그인 시 서버가 설정한 httpOnly 쿠키(`aq_access`, `aq_refresh`) 자동 사용
- JavaScript 토큰 저장 없음 — XSS 노출면 최소화
- 401 응답 시 `POST /auth/refresh`로 무중단 재인증

**통신**:

- REST API (`/api/v1/*`) → FastAPI 백엔드 (`withCredentials: true`)
- WebSocket (`/api/v1/ws/monitoring/{tank_id}`) → 실시간 이벤트 스트림. `tank_id`는 `^[A-Z0-9][A-Z0-9_\-]*$|ALL` 패턴으로 서버에서 검증하며, 형식 위반 시 코드 1008로 즉시 종료.
- Agent API (`/agents/*`) → LangGraph 에이전트 서버

---

### Layer 2 — FastAPI 백엔드

**기술**: FastAPI + SQLAlchemy (async) + PostgreSQL/TimescaleDB + Redis + slowapi

**책임**:

- REST API 엔드포인트 노출
- 인증/인가 (JWT + httpOnly 쿠키, RBAC, 서비스 키)
- DB 읽기/쓰기 (water_quality, fish_growth, feeding, alerts)
- Redis pub/sub 제어 명령 디스패치
- AI 추론 엔진 라이프사이클 관리

**라우터 인증 레이어** (`app/api/router.py`):

```text
Public           /api/v1/auth/*
Superuser only   /api/v1/admin/*          (require_superuser)
Browser users    /api/v1/dashboard/*      (get_current_user)
                 /api/v1/settings/*       (get_current_user)
                 /api/v1/ws/*             (get_current_user)
User or Service  /api/v1/monitoring/*     (require_auth_or_service)
                 /api/v1/control/*        (require_auth_or_service)
                 /api/v1/alerts/*         (require_auth_or_service)
                 /api/v1/water-quality/*  (require_auth_or_service)
                 /api/v1/growth/*         (require_auth_or_service)
                 /api/v1/feeding/*        (require_auth_or_service)
```

`require_auth_or_service`: JWT 쿠키/Bearer **또는** `X-Service-Key` 헤더 허용.

**주요 엔드포인트**:

```text
POST /api/v1/auth/login                         — 로그인 (rate limit 10/min/IP)
POST /api/v1/auth/refresh                       — 토큰 갱신 (쿠키 또는 body)
POST /api/v1/auth/logout                        — 쿠키 삭제
GET  /api/v1/auth/me                            — 현재 사용자 프로필
POST /api/v1/auth/register                      — 신규 사용자 (REGISTRATION_OPEN=true 시에만)
GET  /api/v1/dashboard/summary                  — 대시보드 스냅샷 (Redis 5s 캐시)
GET  /api/v1/dashboard/tanks                    — 수조 목록
GET  /api/v1/monitoring/water-quality/latest    — 최근 수질 데이터
GET  /api/v1/monitoring/water-quality/history   — time_bucket 집계 이력
GET  /api/v1/monitoring/fish-growth/latest      — 최근 성장 데이터
GET  /api/v1/monitoring/feeding/latest          — 최근 급이 기록
GET  /api/v1/alerts/
POST /api/v1/alerts/
PATCH /api/v1/alerts/{id}/resolve
POST /api/v1/control/feeding/trigger
POST /api/v1/control/feeding/stop/{tank_id}
POST /api/v1/control/feeding/adjust
POST /api/v1/control/pump/{tank_id}/{action}
POST /api/v1/control/aeration/increase
POST /api/v1/control/water-exchange
GET  /api/v1/water-quality/predict
GET  /api/v1/growth/count/{tank_id}
GET  /api/v1/feeding/status
WS   /api/v1/ws/monitoring/{tank_id}
```

---

### Layer 3 — 통합 관리 에이전트 (LangGraph)

**기술**: LangGraph + LangChain + Anthropic Claude (claude-sonnet-4-6) + tenacity 재시도 + Redis 영속화

**책임**:

- 하위 최적화 에이전트 조율
- 농장 전체 의사결정 워크플로우
- 자연어 설명 보고서 생성
- 사이클 상태 영속화 + 라이브 이벤트 송출

**그래프 노드**:

```text
collect_data → analyse_situation → [anomaly?] → execute_commands
                                  → [normal]  → generate_report
```

**런타임 계층** (`agents/runtime/`):

- `AgentHTTPClient` — `httpx.AsyncClient` 래퍼. `X-Service-Key` 헤더 자동 주입, 5/10/10/5초 타임아웃, 5xx/429/connect 오류 시 `@retry_http` 데코레이터(3회, 지수 0.5→4s 백오프)로 재시도.
- `LLMClient` — `anthropic.AsyncAnthropic` 래퍼. `@retry_llm` 데코레이터(4회, 랜덤 지수 1→20s 백오프). 60초 기본 타임아웃.
- `StateStore` — Redis 키 `agents:last:management`, `agents:last:optimization:{tank}`, `agents:history:*`. 50개 capped LIST. Redis 다운 시 자동으로 `_InMemoryStateStore` 폴백.
- `EventBus` — Redis pub/sub 채널 `agents:events`. 11종 이벤트 타입 (`cycle_started`, `node_started`, `decision_made`, `command_executed`, `optimization_completed`, `error` 등). `bus.timed_node()` 컨텍스트로 자동 시작/완료 + `duration_ms` 측정.
- `require_service_key` — `/run`, `/optimize` 에 적용된 `X-Service-Key` 의존성.

**다중 탱크 스케줄러**: `main.py::_scheduler()` 가 `settings.default_tank_ids` (기본 `TANK-01,TANK-02,TANK-03`) 를 매 `cycle_interval_seconds` (기본 300초) 마다 순회.

**SSE 엔드포인트**: `GET /events/stream` (sse-starlette) — `agents:events` 채널 구독을 `event: agent\ndata: <json>` 으로 변환. `event: ping` keepalive 포함.

**이력 엔드포인트**: `GET /history?n=20`, `GET /history/optimization?n=20` — `StateStore` 에서 직접 조회.

**백엔드 인증**: `AgentHTTPClient` 가 모든 outbound 요청에 `X-Service-Key` 헤더 자동 주입.

---

### Layer 4 — 최적화 에이전트 (LangGraph Subgraph)

**기술**: LangGraph + 디지털 트윈 ODE 시뮬레이터

**책임**:

- 3개 AI 모듈 출력 종합
- 제어 액션 후보 생성 (Claude LLM)
- 디지털 트윈 시뮬레이션 검증
- 최적 제어 명령 선택

**그래프 노드**:

```text
gather_module_outputs → generate_candidates → simulate_in_twin → select_optimal
```

---

### Layer 5 — RASbit AI 모듈

#### 성장관리 AI (`ai_modules/growth/`)

- **입력**: 카메라 프레임 (JPEG)
- **모델**: YOLOv8 fish detection
- **출력**: fish\_count, avg\_length\_cm, avg\_weight\_g, biomass\_kg

#### 먹이효율 AI (`ai_modules/feeding/`)

- **입력**: 카메라 프레임 (급이 기간)
- **모델**: ResNet18 회귀 분류기
- **출력**: activity\_score (0–1), recommended\_amount\_kg

#### 수질관리 AI (`ai_modules/water_quality/`)

- **입력**: 24시간 물리 센서 시계열 (온도, pH, DO, 탁도)
- **모델**: LSTM/TimesNet (seq2seq) + MC-Dropout 불확실성 추정
- **출력**: ammonia\_ppm, nitrite\_ppm, confidence scores, 신뢰구간

---

### Layer 6 — MLOps 파이프라인

```text
Edge Device
    │
    ├── Camera → CameraCollector → Data Lake (S3/MinIO) → CVAT Labeling
    │                                                          │
    │                                              Training Pipeline (MLflow)
    │                                                          │
    │                                              QualityGate (자동 프로모션)
    │                                                          │
    └── Sensor → SensorCollector ──────→ PostgreSQL/TimescaleDB
                      │
                      └── VirtualSensor (ODE 기반 암모니아/아질산 예측)
```

**MLflow 등록 모델**:

- `FishDetection` — YOLOv8 fish detection
- `FeedingActivityClassifier` — 급이 활성도 분류
- `WaterQualityPredictor` — 수질 예측 LSTM

**MLOps 라이브러리**:

- **AutoML** (`mlops/training/automl.py`): 신규 샘플 수 임계값 도달 시 자동 재훈련 + QualityGate 평가, PSI ≥ 0.20 시 긴급 트리거
- **드리프트 감지** (`mlops/evaluation/drift_detector.py`): PSI + KL-divergence 기반 데이터 드리프트 감지
- **A/B 테스트** (`mlops/registry/mlflow_registry.py`): Canary 프로모션 + 요청별 모델 선택
- **엣지 배포** (`mlops/deployment/edge_deployer.py`): ONNX export + SCP/SSH OTA 배포

**MLOps 런타임 서비스**:

- **`mlops_scheduler`** (상시 컨테이너, HTTP 없음): `OrchestratorScheduler` 가 AutoML 60분 + Drift 15분 사이클을 `schedule` 라이브러리로 실행. 각 사이클은 JSONL 감사 로그(`/data/audit/automl.jsonl`)에 이벤트 기록. 8 MiB 초과 시 자동 로테이션.
- **`mlops_api`** (FastAPI :8002): 조회 엔드포인트 `/health`, `/registry`, `/audit`, `/drift` + 관리자 엔드포인트 `/retrain`, `/promote`, `/deploy` (`X-Service-Key` 필수). MLflow 호출은 모두 `CircuitBreaker` (3-상태, 5회 실패 OPEN, 30초 후 HALF_OPEN) + `ResponseCache` (30초 TTL, `get_stale()` 무제한 폴백) 를 통과.
- **백엔드 프록시** (`backend/app/api/v1/mlops.py`): 브라우저 → 백엔드 (쿠키 인증) → `mlops_api` (`X-Service-Key` 자동 주입). 읽기는 그대로 포워딩, 쓰기는 `require_superuser` 게이팅.

**감사 로그 이벤트 타입**: `automl`, `drift`, `promotion`, `rollback`, `deployment`, `training`, `error` — `mlops/orchestrator/audit_log.py::EventKind` 에 정의.

---

### Layer 7 — 관측성 (선택적)

`docker-compose.observability.yml` 로 동시 기동 가능한 옵션 스택.

**구성요소**:

- **Prometheus** (:9090) — backend / agents / mlops_api 각 서비스의 `/metrics` 엔드포인트를 15초 주기로 스크랩. 잡 라벨로 서비스 구분.
- **Grafana** (:3001) — 대시보드 (기본 admin/admin).
- **OpenTelemetry Collector** (:4317 gRPC, :4318 HTTP) — OTLP 트레이스 수집. `OTEL_EXPORTER_OTLP_ENDPOINT` 환경변수가 설정된 서비스만 송신 (no-op 폴백).

**구현**:

- 각 서비스의 `observability.py` 모듈이 `setup_observability(app, service_name)` 함수를 노출 — `prometheus-fastapi-instrumentator` (메트릭) + OpenTelemetry SDK (트레이스) 를 한 번에 활성화.
- 자동 instrumentation: FastAPI, httpx (3 서비스 공통), SQLAlchemy + Redis (backend / agents), Requests (mlops_api → MLflow).
- Resource attributes: `service.name`, `service.version`, `deployment.environment` 자동 첨부.

---

## 데이터 흐름

### 실시간 모니터링 흐름

```text
SensorPublisher (asyncio loop, 5s)
    → ODE virtual sensor (니트리피케이션 모델)
    → PUBLISH wq:{tank_id}  (Redis)
    → ws_monitoring.py 구독  (WebSocket 팬아웃)
    → 브라우저 실시간 차트 업데이트

SensorPublisher (DB 기록, 30s마다)
    → POST /api/v1/monitoring/water-quality  (내부 호출)
    → water_quality_readings (TimescaleDB hypertable)
    → 임계값 초과 시 Alert 생성
    → PUBLISH events:alerts  (Redis)
    → WebSocket 알림 팬아웃
```

### AI 제어 흐름

```text
ManagementAgent.run()
    → collect_farm_data()    : GET /api/v1/dashboard/summary
    → analyse_situation()    : LLM analysis
    → OptimizationAgent.run() (subgraph)
        → gather_module_outputs()
            : GET /api/v1/monitoring/water-quality/latest
            : GET /api/v1/growth/count/{tank_id}
            : GET /api/v1/feeding/status
        → generate_candidates() : Claude LLM
        → simulate_in_twin()    : 니트리피케이션 ODE (6h horizon)
        → select_optimal()
    → execute_commands()
        : POST /api/v1/control/*  (X-Service-Key 헤더)
        → PUBLISH cmd:{tank_id}:{device}  (Redis)
        → 엣지 디바이스 액추에이터
```

---

## 데이터베이스 스키마

### TimescaleDB Hypertables

- `water_quality_readings` — `measured_at` 기준 일별 청크
- `fish_growth_records` — `measured_at` 기준 주별 청크
- `feeding_records` — `started_at` 기준 주별 청크

### Regular Tables

- `alerts` — 알림 레코드 (`active_alert` 인덱스)
- `users` — 사용자 계정 (`username`, `email` unique)

---

## 보안 설계

| 항목 | 구현 내용 |
|------|-----------|
| 토큰 저장 | httpOnly 쿠키 (`aq_access` path=`/`, `aq_refresh` path=`/api/v1/auth`) |
| JWT | HS256, `iat`+`exp`+`type` 클레임, 액세스/리프레시 별도 시크릿 |
| Rate Limiting | `POST /auth/login` 10/분, `/control/*` 60/분 (내부 서비스 면제), `/alerts/` 30/분 (내부 서비스 면제), `/mlops/{retrain,promote,deploy}` 10/분 (면제 없음). `is_internal_service(request)` 헬퍼가 `X-Service-Key` 일치 시 슬로어피 우회 (`app/core/limiter.py`) |
| RBAC | router-level `Depends()` — superuser / user / service 분리 |
| 서비스 인증 | `X-Service-Key` 헤더 (에이전트 → 백엔드, 백엔드 → mlops_api). 양방향 모두 같은 `INTERNAL_API_KEY` 사용 |
| 등록 제어 | `REGISTRATION_OPEN=false` 기본값 |
| 입력 검증 | `tank_id` 패턴 `^[A-Z0-9][A-Z0-9_\-]*$` (REST `Path()` + WebSocket 런타임 검증), SQL 완전 파라미터화 |
| 요청 본문 한도 | 1 MiB (백엔드 `MAX_REQUEST_BYTES`, agents/mlops_api 동일). 초과 시 413. Fast path (Content-Length) + streaming fallback. |
| 보안 헤더 | Nginx: HSTS · CSP · X-Frame-Options DENY · Referrer-Policy · Permissions-Policy. FastAPI 미들웨어가 동일 헤더를 직접 응답에 추가 (gateway 우회 시에도 보호). |
| CORS — backend | `CORS_ORIGINS` 명시적 origin 목록, `allow_credentials=True` |
| CORS — mlops_api | `MLOPS_CORS_ORIGINS` 기본 빈 값 → 브라우저 직접 호출 차단. 백엔드 프록시만 정당한 경로 |
| 쿠키 | 프로덕션에서 `Secure=true`, `SameSite=Lax` |
| 시크릿 관리 | 환경변수 + K8s Secrets. 프로덕션은 sealed-secrets 또는 SOPS+age 워크플로 (`infra/k8s/secrets/README.md`). `.gitleaks.toml` 으로 CI 시크릿 스캔 |

---

## 확장성 고려사항

- TimescaleDB hypertable을 통한 시계열 데이터 수평 확장
- FastAPI async/await 비동기 처리
- MLflow를 통한 모델 버전 관리 및 무중단 배포
- Docker Compose (개발) → Kubernetes kustomize (운영) — `infra/k8s/`에 HPA, CronJob (AutoML + Postgres 백업), Deployment (mlops_scheduler, mlops_api), Ingress 포함
- GitHub Actions CI: lint → gitleaks 시크릿 스캔 → test (backend / agents / mlops / frontend 4-갈래) → docker build (PR 전용)

---

## 테스트 전략

- **Backend 단위 + 통합** — pytest + pytest-asyncio + aiosqlite. 위치 `backend/tests/`. `make test` 또는 CI 잡 `test-backend` (postgres + redis 서비스 컨테이너).
- **Agents 단위** — pytest-asyncio + fakeredis. 위치 `agents/tests/`. CI 잡 `test-agents` (서비스 컨테이너 없음 — Anthropic / torch 미설치 환경).
- **MLOps 단위** — pytest. 위치 `mlops/tests/`. CI 잡 `test-mlops` (회로차단기 / 감사로그 / drift / 설정).
- **Frontend 단위** — Vitest + React Testing Library + jsdom. 위치 `frontend/src/**/*.test.{ts,tsx}`. `cd frontend && npm test` 또는 CI 잡 `test-frontend`.
- **Frontend E2E** — Playwright (Chromium). 위치 `frontend/e2e/`. `npm run e2e` (stack 기동 후).
- **부하 테스트** — k6 (REST / WebSocket / SSE). 위치 `load/*.k6.js`. 로컬 수동 실행; CI 대신 별도 호스트 권장.
- **시크릿 스캔** — gitleaks (`.gitleaks.toml`). CI 잡 `secret-scan` (`fetch-depth: 0`).

**런타임 신뢰성 검증**:

- `MockEventSource` / `MockWebSocket` 폴리필 (`frontend/src/test/setup.ts`) — jsdom 에 없는 브라우저 API 를 imperative 제어 가능한 stub 으로 대체. SSE/WS 재연결 정책을 fake timer 로 직접 검증.
- `CircuitBreaker` / `ResponseCache` (`mlops/api/resilience.py`) — 11개 테스트로 상태 전이 + 캐시 폴백 + cold-start 동작 검증.
- `useEventSource` / `useWebSocket` — 16개 테스트로 reconnect / buffer trim / unmount cleanup / send no-op 등 엣지 동작 검증.

**프론트 글로벌 에러 차단**: `<ErrorBoundary>` 컴포넌트가 두 레이어로 적용 — `<App>` 최외곽 + `<AppLayout>` per-route. 컴포넌트 크래시가 흰 화면을 만들지 않으며, fallback UI 는 인라인 스타일로 Tailwind 의존성 없이 렌더.
