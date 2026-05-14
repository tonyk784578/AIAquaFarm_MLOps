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
- 알림 수신 및 해결 인터페이스
- 장비 원격 제어 패널
- WebSocket 기반 실시간 데이터 수신

**페이지 구성**:

| 경로 | 컴포넌트 | 설명 |
| ---- | -------- | ---- |
| `/dashboard` | `Dashboard/index.tsx` | KPI 요약 + 수질·성장·급이·알림 패널 |
| `/water-quality` | `WaterQuality/WaterQualityPage.tsx` | 수질 지표 상세 + 24h 이력 차트 |
| `/control` | `Control/ControlPanel.tsx` | 장치 원격 제어 |
| `/growth` | `Growth/GrowthPage.tsx` | 어류 성장 추이 |
| `/feeding` | `Feeding/FeedingPage.tsx` | 급이 이벤트 및 활성도 |
| `/alerts` | `Alerts/AlertsPage.tsx` | 알림 목록 및 해제 |
| `/mlops` | `MLOps/MLOpsPage.tsx` | 에이전트 상태·모델 레지스트리 |
| `/settings` | `Settings/SettingsPage.tsx` | 임계값·모델 상태 설정 |

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

**기술**: LangGraph + LangChain + Anthropic Claude (claude-sonnet-4-6)

**책임**:

- 하위 최적화 에이전트 조율
- 농장 전체 의사결정 워크플로우
- 자연어 설명 보고서 생성

**그래프 노드**:

```text
collect_data → analyse_situation → [anomaly?] → execute_commands
                                  → [normal]  → generate_report
```

**백엔드 인증**: 모든 httpx 요청에 `X-Service-Key: {backend_api_key}` 헤더 자동 주입 (`_svc_headers()` / `_service_headers()` 헬퍼).

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

**MLOps 자동화 기능**:

- **AutoML** (`mlops/training/automl.py`): 신규 샘플 수 임계값 도달 시 자동 재훈련 + QualityGate 평가
- **드리프트 감지** (`mlops/evaluation/drift_detector.py`): PSI + KL-divergence 기반 데이터 드리프트 감지
- **A/B 테스트** (`mlops/registry/mlflow_registry.py`): Canary 프로모션 + 요청별 모델 선택
- **엣지 배포** (`mlops/deployment/edge_deployer.py`): ONNX export + SCP/SSH OTA 배포

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
| Rate Limiting | `POST /auth/login` IP당 10회/분 (slowapi) |
| RBAC | router-level `Depends()` — superuser / user / service 분리 |
| 서비스 인증 | `X-Service-Key` 헤더 (에이전트 → 백엔드) |
| 등록 제어 | `REGISTRATION_OPEN=false` 기본값 |
| 입력 검증 | `tank_id` 패턴 `^[A-Z0-9][A-Z0-9_\-]*$` (REST `Path()` + WebSocket 런타임 검증), SQL 완전 파라미터화 |
| CORS | 명시적 origin 목록, `allow_credentials=True` |
| 쿠키 | 프로덕션에서 `Secure=true`, `SameSite=Lax` |
| 시크릿 관리 | 환경변수 전용, K8s Secrets로 주입 (하드코딩 금지) |

---

## 확장성 고려사항

- TimescaleDB hypertable을 통한 시계열 데이터 수평 확장
- FastAPI async/await 비동기 처리
- MLflow를 통한 모델 버전 관리 및 무중단 배포
- Docker Compose (개발) → Kubernetes kustomize (운영) — `infra/k8s/`에 HPA, CronJob, Ingress 포함
- GitHub Actions CI: lint → test (PostgreSQL+Redis 서비스 컨테이너) → docker build (PR 전용)
