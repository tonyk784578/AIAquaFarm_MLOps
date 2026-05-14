# AIAquafarm — AI 기반 스마트 RAS 양식장 플랫폼

RAS(순환여과식, Recirculating Aquaculture System) 양식장을 위한 **AI 통합 관리 플랫폼**입니다.
비전 AI·시계열 예측·LangGraph 멀티에이전트·MLOps 파이프라인을 결합하여
수질 관리·어류 성장·먹이 급이를 실시간으로 자동화합니다.

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [아키텍처](#2-아키텍처)
3. [기술 스택](#3-기술-스택)
4. [빠른 시작](#4-빠른-시작)
5. [첫 번째 계정 만들기](#5-첫-번째-계정-만들기)
6. [접속 주소](#6-접속-주소)
7. [개발 명령어](#7-개발-명령어)
8. [프로젝트 구조](#8-프로젝트-구조)
9. [핵심 기능 설명](#9-핵심-기능-설명)
10. [데이터 흐름](#10-데이터-흐름)
11. [AI 모델](#11-ai-모델)
12. [MLOps 파이프라인](#12-mlops-파이프라인)
13. [인증 구조](#13-인증-구조)
14. [환경 변수 가이드](#14-환경-변수-가이드)
15. [프로덕션 체크리스트](#15-프로덕션-체크리스트)
16. [구현 현황](#16-구현-현황)
17. [알려진 이슈 및 해결 이력](#17-알려진-이슈-및-해결-이력)

---

## 1. 시스템 개요

### 이 플랫폼이 해결하는 문제

RAS 양식장은 수질·먹이·성장을 24시간 모니터링하고 제어해야 합니다.
전통적인 수동 운영에서는 다음 문제가 반복됩니다:

| 문제 | 결과 |
|------|------|
| 암모니아·아질산 급증 지연 감지 | 집단 폐사 |
| 경험에 의존한 급이량 결정 | 사료 낭비 또는 영양 부족 |
| 어류 성장 계측 인력 소모 | 수확 시기 오판 |
| 이상 상황 야간 미감지 | 대응 골든타임 상실 |

AIAquafarm은 이 모든 과정을 **AI가 자동으로 감지·예측·제어**합니다.

### 주요 기능

- **실시간 수질 모니터링**: LSTM 모델로 암모니아·아질산 농도 예측, 임계값 초과 시 즉시 알림
- **비전 기반 성장 추적**: YOLOv8으로 어류 개체 감지·계수·체장 측정 자동화
- **AI 급이 최적화**: ResNet18으로 먹이 활성도 분류, 적정 급이량 자동 계산
- **LangGraph AI 에이전트**: Claude가 농장 상태를 분석하고 제어 명령을 자율 실행
- **디지털 트윈 시뮬레이션**: 제어 명령 실행 전 ODE 시뮬레이터로 결과 사전 검증
- **MLOps 자동화**: 데이터 드리프트 감지 → 자동 재학습 → QualityGate → 배포

---

## 2. 아키텍처

```text
브라우저 (React)
    │
    ▼ HTTP/WebSocket (Port 80)
┌─────────────────────────────────────────────────────┐
│  Nginx Gateway (포트 분기 + 정적 파일 서빙)           │
│  /api/*  → backend:8000                             │
│  /*      → frontend:80 (React SPA)                  │
└──────────┬──────────────────────────────────────────┘
           │
    ┌──────▼───────────────────────────────────────┐
    │  FastAPI 백엔드 (backend:8000)               │
    │                                              │
    │  ┌─────────────┐  ┌───────────────────────┐ │
    │  │  REST API   │  │  WebSocket            │ │
    │  │  인증/RBAC  │  │  /api/v1/ws/{tank_id} │ │
    │  │  Rate Limit │  │  Redis 실시간 구독    │ │
    │  └─────────────┘  └───────────────────────┘ │
    │                                              │
    │  ┌─────────────────────────────────────────┐ │
    │  │  AI 추론 엔진 (app.state에 싱글턴 보관) │ │
    │  │  WaterQuality · Growth · Feeding        │ │
    │  └─────────────────────────────────────────┘ │
    └──────────────────────────────────────────────┘
           │ X-Service-Key 인증
    ┌──────▼───────────────────────────────────────┐
    │  LangGraph 에이전트 (agents:8001)             │
    │                                              │
    │  management_graph:                           │
    │    collect_data → analyse → execute → report │
    │                                              │
    │  optimization_subgraph:                      │
    │    gather_outputs → generate_candidates      │
    │    → twin_sim (ODE) → select_optimal         │
    └──────────────────────────────────────────────┘
           │
    ┌──────▼───────────────────────────────────────┐
    │  데이터 레이어                                │
    │  PostgreSQL/TimescaleDB  Redis (pub/sub)     │
    │  MLflow (모델 레지스트리)  S3 (데이터 레이크) │
    └──────────────────────────────────────────────┘
```

### 실시간 데이터 파이프라인

```text
VirtualSensor (ODE 시뮬레이터)
    │ 5초마다 PUBLISH
    ▼
Redis 채널: wq:{tank_id}
    │
    ├─→ WebSocket 핸들러 → 브라우저 실시간 갱신
    └─→ DB 기록 (30초마다 PostgreSQL)
```

### Redis 채널 규칙

| 채널 | 용도 |
|------|------|
| `wq:{tank_id}` | 수질 센서 데이터 실시간 스트림 |
| `cmd:{tank_id}:{device}` | 제어 명령 (feeder·pump·aeration·exchange) |
| `events:alerts` | 알림 이벤트 브로드캐스트 |

---

## 3. 기술 스택

| 계층 | 기술 | 역할 |
|------|------|------|
| **프론트엔드** | React 18, TypeScript, Vite, TailwindCSS | 대시보드 UI |
| | React Query, Axios, React Router | 서버 상태·API·라우팅 |
| | Recharts | 실시간 차트 시각화 |
| | Zustand (persist) | 클라이언트 상태 (다크 모드 등) |
| **백엔드** | FastAPI, Uvicorn (4 workers) | REST + WebSocket API |
| | SQLAlchemy 2.0 (async), asyncpg | 비동기 ORM |
| | Alembic | DB 스키마 마이그레이션 |
| | Pydantic v2, pydantic-settings | 스키마 검증·설정 관리 |
| | slowapi | Rate Limiting |
| **인증** | python-jose (JWT), bcrypt | 토큰·비밀번호 |
| **AI 에이전트** | LangGraph, LangChain | 멀티에이전트 워크플로우 |
| | Anthropic Claude (claude-sonnet-4-6) | LLM 추론·tool-use |
| **AI 모델** | PyTorch 2.3+, Ultralytics YOLOv8 | 딥러닝 추론 |
| | ResNet18 (분류), LSTM/TimesNet (시계열) | 모델 아키텍처 |
| **MLOps** | MLflow 2.13+ | 실험 추적·모델 레지스트리 |
| | boto3, S3 | 데이터 레이크 |
| **데이터베이스** | PostgreSQL 15 + TimescaleDB | 시계열 hypertable |
| **캐시·브로커** | Redis 7 | pub/sub, WebSocket fan-out, 캐싱 |
| **컨테이너** | Docker Compose | 개발·스테이징 환경 |
| | Kubernetes + kustomize | 프로덕션 오케스트레이션 |
| **CI/CD** | GitHub Actions | lint → test → docker build |
| **코드 품질** | ruff, structlog, pytest | 린터·로깅·테스트 |

---

## 4. 빠른 시작

### 사전 요구사항

- Docker ≥ 24.0
- Docker Compose ≥ 2.20
- GNU Make
- (AI 에이전트 사용 시) Anthropic API Key

### Step 1 — 환경 파일 설정

```bash
cp .env.example .env
```

`.env` 필수 설정값:

```bash
# JWT 시크릿 (각각 다른 랜덤값 사용)
SECRET_KEY=$(openssl rand -hex 32)
JWT_REFRESH_SECRET_KEY=$(openssl rand -hex 32)

# 에이전트↔백엔드 내부 인증 키 (같은 값으로 설정)
INTERNAL_API_KEY=$(openssl rand -hex 24)
BACKEND_API_KEY=<INTERNAL_API_KEY와 동일한 값>

# Claude 에이전트 (필수)
ANTHROPIC_API_KEY=sk-ant-...

# CORS 허용 오리진 (브라우저에서 접근할 주소)
# 주의: http://localhost:80 과 http://localhost 는 다름 — 둘 다 넣어야 함
CORS_ORIGINS=["http://localhost:3000","http://localhost:80","http://localhost"]
```

### Step 2 — 전체 서비스 빌드 및 시작

```bash
make build       # Docker 이미지 빌드 (최초 1회, 약 5~10분)
make up          # 전체 서비스 컨테이너 시작
make migrate     # Alembic DB 마이그레이션 실행 (최초 1회)
make seed        # 테스트 데이터 삽입 (선택, 7일치 525건)
```

### Step 3 — 서비스 확인

```bash
make health
```

정상 출력:

```text
AIAquafarm Service Health Check

  ✓ Backend API      (localhost:8000)
  ✓ MLflow           (localhost:5000)
  ✓ Agents           (localhost/agents)
  ✓ Nginx gateway    (localhost:80)
```

### Step 4 — 개발 모드 (hot-reload)

```bash
make dev   # 백엔드 코드 변경 시 자동 반영
```

### (선택) 프론트엔드 로컬 dev 서버

Docker 없이 프론트엔드만 실행하거나 최신 UI 변경사항을 즉시 확인할 때 사용합니다.

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (백엔드 자동 프록시)
```

**Mock 모드** — 백엔드 없이 UI만 개발할 때:

```bash
# frontend/.env.local
VITE_USE_MOCK=true
```

`VITE_USE_MOCK=true` 설정 시 모든 API 호출이 `src/mocks/` 의 결정론적 목 데이터로 intercept됩니다.
실제 네트워크 요청은 발생하지 않으며, 로그인 포함 전체 UI를 오프라인으로 동작시킬 수 있습니다.

---

## 5. 첫 번째 계정 만들기

회원가입은 기본적으로 비활성화(`REGISTRATION_OPEN=false`)되어 있습니다.
아래 방법으로 최초 슈퍼유저를 생성하세요:

```bash
docker compose exec backend python3 -c "
import asyncio, bcrypt
from app.db.session import AsyncSessionLocal
from app.models.user import User

pw = bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode()

async def main():
    async with AsyncSessionLocal() as s:
        s.add(User(
            username='admin',
            email='admin@example.com',
            hashed_password=pw,
            full_name='Administrator',
            is_active=True,
            is_superuser=True,
        ))
        await s.commit()
        print('계정 생성 완료')

asyncio.run(main())
"
```

이후 `http://localhost`에 접속하여 방금 설정한 username/password로 로그인합니다.

> **비밀번호 길이**: bcrypt는 최대 72바이트까지 지원합니다.

---

## 6. 접속 주소

| 서비스 | URL | 비고 |
|--------|-----|------|
| **대시보드** | <http://localhost> | 메인 React 앱 |
| **API Swagger** | <http://localhost:8000/api/docs> | REST API 문서 |
| **API ReDoc** | <http://localhost:8000/api/redoc> | 대안 API 문서 |
| **Agents API** | <http://localhost/agents/health> | nginx 통해 접근 |
| **MLflow UI** | <http://localhost:5000> | 모델 레지스트리·실험 |

> **참고**: agents 서비스(포트 8001)는 호스트에 직접 노출되지 않습니다.
> 외부에서는 nginx의 `/agents/` 경로를 통해 접근합니다.

---

## 7. 개발 명령어

```bash
# 인프라
make up              # 전체 서비스 시작
make down            # 전체 서비스 중지
make build           # 이미지 빌드
make rebuild         # 이미지 캐시 없이 재빌드
make restart         # 전체 재시작
make health          # 서비스 헬스체크

# 로그
make logs            # 전체 서비스 로그 (실시간)
make logs-backend    # 백엔드 로그만
make logs-agents     # 에이전트 로그만

# DB
make migrate                          # 마이그레이션 적용
make makemigration MSG="설명"         # 새 마이그레이션 생성
make seed                             # 테스트 데이터 삽입

# 개발
make dev             # hot-reload 모드
make shell           # 백엔드 컨테이너 bash
make shell-agents    # 에이전트 컨테이너 bash

# 코드 품질
make lint            # ruff 린터 실행
make format          # ruff 포맷터 실행
make test            # pytest 실행
make test-cov        # 커버리지 포함 테스트

# 정리
make clean           # 컨테이너·볼륨·이미지 삭제
```

### 합성 학습 데이터 생성 (컨테이너 없이)

```bash
python scripts/generate_wq_test_data.py --days 30 --tanks 3 --output data/wq.csv
python scripts/generate_feeding_test_data.py --output data/feeding_dataset/ --n-per-class 200
python scripts/generate_growth_test_data.py --output data/growth_dataset/ --n-train 800
```

---

## 8. 프로젝트 구조

```text
AIAquafarm_MLOps/
│
├── backend/                    # FastAPI 백엔드 서버
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/             # REST 엔드포인트
│   │   │   │   ├── auth.py         → 로그인·로그아웃·토큰 갱신
│   │   │   │   ├── dashboard.py    → 대시보드 집계 API
│   │   │   │   ├── monitoring.py   → 수질·성장·급이 데이터 기록
│   │   │   │   ├── control.py      → 장치 제어 명령
│   │   │   │   ├── alerts.py       → 알림 조회·해제
│   │   │   │   ├── ws_monitoring.py → WebSocket 실시간 스트림
│   │   │   │   └── ...
│   │   │   ├── deps.py         → require_auth_or_service 의존성
│   │   │   └── router.py       → 라우터 등록 및 인증 계층 분기
│   │   ├── core/
│   │   │   ├── security.py     → JWT 생성·검증, bcrypt 해싱
│   │   │   └── limiter.py      → slowapi Rate Limiter
│   │   ├── db/
│   │   │   ├── session.py      → async SQLAlchemy 엔진·세션
│   │   │   └── redis.py        → Redis 클라이언트 싱글턴
│   │   ├── models/             → SQLAlchemy ORM 모델
│   │   ├── schemas/            → Pydantic 입출력 스키마
│   │   ├── services/
│   │   │   ├── monitoring_service.py  → 집계 쿼리 + Redis 5초 캐시
│   │   │   ├── sensor_publisher.py   → VirtualSensor → Redis pub
│   │   │   ├── water_quality_service.py
│   │   │   ├── growth_service.py
│   │   │   └── feeding_service.py
│   │   ├── config.py           → pydantic-settings (환경변수 로딩)
│   │   └── main.py             → FastAPI 앱 생성·lifespan 등록
│   ├── alembic/versions/       → DB 마이그레이션 스크립트
│   └── tests/                  → pytest 테스트
│
├── agents/                     # LangGraph AI 에이전트
│   ├── management_agent/
│   │   ├── graph.py            → 관리 그래프 정의
│   │   ├── nodes.py            → collect / analyse / execute / report
│   │   ├── tools.py            → decide_control_action (Claude tool-use)
│   │   └── state.py            → AgentState TypedDict
│   ├── optimization_agent/
│   │   ├── graph.py            → 최적화 서브그래프
│   │   ├── optimizer.py        → RuleBasedOptimizer (LLM 실패 폴백)
│   │   └── twin_sim.py         → 니트리피케이션 ODE 디지털 트윈
│   ├── config.py               → AgentSettings (ANTHROPIC_API_KEY 등)
│   └── main.py                 → FastAPI 앱 (POST /run, POST /optimize)
│
├── ai_modules/                 # 핵심 AI 추론 모듈 (FastAPI 의존성 없음)
│   ├── water_quality/
│   │   ├── model.py            → LSTM/TimesNet PyTorch 래퍼
│   │   ├── feature_engineering.py → FeatureScaler, WindowBuilder
│   │   ├── virtual_sensor.py   → ODE 기반 가상 센서
│   │   ├── mlflow_loader.py    → MLflow 레지스트리에서 모델 로딩
│   │   └── schemas.py          → Pydantic I/O 스키마
│   ├── growth/
│   │   ├── model.py            → YOLOv8 래퍼 (FishDetectionModel)
│   │   ├── size_estimator.py   → 픽셀→실제 크기 변환
│   │   └── schemas.py
│   └── feeding/
│       ├── model.py            → ResNet18 분류 모델
│       └── schemas.py
│
├── mlops/                      # MLOps 자동화 파이프라인
│   ├── training/
│   │   ├── train_water.py      → 수질 모델 학습 스크립트
│   │   ├── train_feeding.py    → 급이 모델 학습 스크립트
│   │   ├── train_growth.py     → 성장 모델 학습 스크립트
│   │   └── automl.py           → AutoML (샘플 임계값·드리프트 기반 자동 재학습)
│   ├── evaluation/
│   │   ├── evaluator.py        → QualityGate + ModelEvaluator
│   │   └── drift_detector.py   → PSI + KL-divergence 드리프트 감지
│   ├── registry/
│   │   └── mlflow_registry.py  → 서명 검증 후 레지스트리 등록·A/B 카나리
│   ├── data_lake/
│   │   └── storage.py          → S3 데이터 레이크 (raw/{camera|sensor|labelled}/...)
│   └── data_collector/
│       └── sensor_collector.py → 엣지 센서 수집기 (mlops_worker 진입점)
│
├── frontend/                   # React 대시보드
│   ├── src/
│   │   ├── components/
│   │   │   ├── Auth/           → 로그인 페이지
│   │   │   ├── Dashboard/      → 수질·성장·급이·알림 패널 + KPI 요약
│   │   │   ├── WaterQuality/   → 수질 상세 페이지 (/water-quality)
│   │   │   ├── Control/        → 장치 제어 패널
│   │   │   ├── Alerts/         → 알림 목록
│   │   │   ├── Growth/         → 성장 관리 페이지
│   │   │   ├── Feeding/        → 먹이 관리 페이지
│   │   │   ├── MLOps/          → MLOps 상태 페이지
│   │   │   ├── Settings/       → 모델 상태·임계값 설정
│   │   │   └── Layout/         → Header (다크모드 토글·알림 벨)·Sidebar
│   │   ├── context/
│   │   │   └── AuthContext.tsx → httpOnly 쿠키 기반 인증 상태
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts → WebSocket 자동 재연결
│   │   ├── mocks/
│   │   │   ├── data.ts         → 결정론적 목 데이터 생성기 (수질·성장·급이·알림)
│   │   │   └── setup.ts        → axios 어댑터 기반 mock 인터셉터 (VITE_USE_MOCK=true)
│   │   ├── stores/
│   │   │   └── themeStore.ts   → Zustand persist 다크 모드 토글 (localStorage: aq-theme)
│   │   ├── services/
│   │   │   └── api.ts          → axios 클라이언트 (apiClient·agentClient)
│   │   └── types/index.ts      → 공유 TypeScript 타입
│   └── nginx.conf              → SPA 라우팅 + /api · /agents 프록시
│
├── infra/
│   ├── nginx/nginx.conf        → 게이트웨이 nginx (포트 80)
│   ├── postgres/init.sql       → TimescaleDB hypertable 초기화
│   ├── redis/redis.conf        → Redis 설정
│   ├── mlflow/Dockerfile       → MLflow 서버 이미지
│   └── k8s/                   → Kubernetes 매니페스트
│
├── scripts/
│   ├── seed_data.py            → 테스트 데이터 삽입 (make seed)
│   ├── generate_wq_test_data.py
│   ├── generate_feeding_test_data.py
│   └── generate_growth_test_data.py
│
├── docs/                       → 상세 문서 (api-spec, setup-guide, architecture)
├── docker-compose.yml          → 프로덕션 컨테이너 정의
├── docker-compose.dev.yml      → 개발 오버라이드 (hot-reload)
├── Makefile                    → 개발 편의 명령어
└── .env.example                → 환경변수 템플릿
```

---

## 9. 핵심 기능 설명

### 대시보드 (`/dashboard`)

- **KPI 요약 행**: 운영 중 수조 수·활성 알림 수·총 바이오매스·현재 수온/DO
- **수질 패널**: 실시간 온도·pH·DO·탁도·암모니아·아질산 수치, AI 예측값
- **성장 패널**: 평균 체장·체중·마리수·생체중·FCR(사료전환율) 추이
- **급이 패널**: 최근 급이 이벤트, 권장 급이량 vs 실제 급이량
- **알림 패널**: 활성 경보 (심각도: critical·warning·info)
- **WebSocket 토스트**: 새 알림 수신 시 화면 우하단에 8초간 팝업

### 수질 모니터링 (`/water-quality`)

- 수조별 현재 수질 지표 상세 조회
- 24시간 이력 차트 (Recharts): 온도·pH·DO·암모니아·아질산·탁도
- 임계값 위반 시 인라인 경고 표시

### 제어 패널 (`/control`)

수조별로 다음 장치를 직접 제어합니다:
- **먹이 공급기** (feeder): 급이 시작/중지, 비상 정지
- **순환 펌프** (pump): 유량 조절
- **폭기 장치** (aeration): 용존산소 보충
- **환수** (exchange): 수질 악화 시 물 교체

### 설정 페이지 (`/settings`)

- AI 모델 상태 카드 (로딩 상태·버전·MLflow 연결 여부)
- 수질 임계값 조정 (암모니아·아질산 경보 기준)

### AI 에이전트 자동 주기

에이전트는 **2분마다** 관리 사이클을 실행합니다:
1. `collect_data`: 대시보드 데이터·알림·수질 예측 수집
2. `analyse_situation`: Claude가 상황 분석, 최적화 서브그래프 호출
3. `execute_commands` (필요 시): 실제 제어 명령 실행
4. `generate_report`: 사이클 결과 로그 기록

---

## 10. 데이터 흐름

### 수질 데이터 (실시간)

```text
VirtualSensor.step()          # 5초마다 ODE 적분
    → SensorPublisher         # Redis PUBLISH wq:{tank_id}
    → WebSocket 핸들러        # 브라우저로 즉시 전송
    → DB 기록 (30초마다)      # TimescaleDB water_quality_readings
```

### AI 예측 요청

```text
클라이언트 POST /api/v1/water-quality/predict
    → WaterQualityInferenceEngine (app.state)
    → LSTM 모델 추론
    → 임계값 비교 → 알림 생성 (DB + Redis events:alerts)
```

### 제어 명령

```text
클라이언트 POST /api/v1/control/{tank_id}/{device}
    → ControlService.execute()
    → DB feeding_records / DB 이벤트 기록
    → Redis PUBLISH cmd:{tank_id}:{device}
    → 엣지 장치 수신
```

---

## 11. AI 모델

### 수질 예측 (Water Quality)

| 항목 | 내용 |
|------|------|
| 모델 | LSTM / TimesNet |
| 입력 | 최근 24시간 수질 시계열 (8개 특성) |
| 출력 | 향후 암모니아·아질산 농도 예측 + 신뢰구간 |
| 특이점 | MC-Dropout으로 불확실성 정량화 |
| MLflow 이름 | `WaterQualityPredictor` |

### 어류 성장 감지 (Fish Growth)

| 항목 | 내용 |
|------|------|
| 모델 | YOLOv8 (객체 감지) |
| 입력 | 카메라 프레임 이미지 |
| 출력 | 개체 수·평균 체장(cm)·추정 체중(g)·생체중(kg) |
| MLflow 이름 | `FishDetection` |

### 먹이 활성도 분류 (Feeding Activity)

| 항목 | 내용 |
|------|------|
| 모델 | ResNet18 (이미지 분류) |
| 입력 | 수면 이미지 |
| 출력 | 활성도 점수 (0.0~1.0) → 적정 급이량 |
| MLflow 이름 | `FeedingActivityClassifier` |

### 모델 장애 내성

모든 AI 모델은 `is_ready` 플래그로 상태를 관리하며,
모델 미로딩 시에도 **기본값(mock)을 반환**하고 절대 요청 경로에서 예외를 발생시키지 않습니다.

---

## 12. MLOps 파이프라인

### 모델 생명주기

```text
None → Staging → Production → Archived
```

`ModelEvaluator`만 스테이지 전환 권한을 가집니다. 학습 스크립트에서 직접 승격하지 않습니다.

### 자동 재학습 트리거

`AutoMLPipeline.check_and_retrain()`은 다음 조건에서 재학습을 시작합니다:
- 신규 데이터 샘플 수 ≥ 임계값 (모델별 설정)
- PSI(Population Stability Index) 드리프트 감지

### QualityGate

재학습된 모델은 `ModelEvaluator`의 지표 임계값을 통과해야 `Production`으로 승격됩니다.

---

## 13. 인증 구조

### 브라우저 클라이언트

```text
POST /api/v1/auth/login  →  httpOnly 쿠키 설정
                              aq_access  (1일, path=/)
                              aq_refresh (7일, path=/api/v1/auth)
↓
이후 모든 요청: 쿠키 자동 첨부 (JS 접근 불가)
↓
401 수신 시: POST /api/v1/auth/refresh → 자동 토큰 갱신
```

### 내부 서비스 (에이전트)

```text
요청 헤더: X-Service-Key: <INTERNAL_API_KEY>
→ require_auth_or_service 의존성이 JWT 또는 서비스 키 둘 다 허용
```

### 엔드포인트 인증 계층

| 계층 | 적용 라우터 | 허용 |
|------|------------|------|
| 공개 | `/api/v1/auth/*` | 누구나 |
| 사용자 + 서비스 | `/api/v1/dashboard/*`, `/api/v1/monitoring/*`, `/api/v1/control/*`, `/api/v1/alerts/*`, AI 엔드포인트 | JWT 쿠키 **또는** X-Service-Key |
| 사용자 전용 | `/api/v1/settings/*`, `/api/v1/ws/*` | JWT 쿠키만 |
| 슈퍼유저 전용 | `/api/v1/admin/*` | 슈퍼유저 JWT |

---

## 14. 환경 변수 가이드

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `SECRET_KEY` | ✅ | dev_secret | JWT 액세스 토큰 서명 키 |
| `JWT_REFRESH_SECRET_KEY` | ✅ | - | JWT 리프레시 토큰 서명 키 (SECRET_KEY와 달라야 함) |
| `INTERNAL_API_KEY` | ✅ | - | 에이전트→백엔드 서비스 인증 키 |
| `BACKEND_API_KEY` | ✅ | - | INTERNAL_API_KEY와 동일 값 |
| `ANTHROPIC_API_KEY` | ✅ | - | Claude AI 에이전트 API 키 |
| `POSTGRES_PASSWORD` | ✅ | aquafarm_secret | PostgreSQL 비밀번호 |
| `CORS_ORIGINS` | ✅ | localhost:3000, localhost | CORS 허용 오리진 (JSON 배열) |
| `VITE_USE_MOCK` | - | false | 프론트엔드 목 데이터 모드 (`frontend/.env.local`에 설정) |
| `REGISTRATION_OPEN` | - | false | 회원가입 활성화 (초기 셋업 시만 true) |
| `COOKIE_SECURE` | - | false | HTTPS 쿠키 (프로덕션 true) |
| `LOG_LEVEL` | - | info | 로그 레벨 |
| `DEBUG` | - | false | SQLAlchemy 쿼리 로깅 |
| `MLFLOW_TRACKING_URI` | - | http://mlflow:5000 | MLflow 서버 주소 |
| `DEFAULT_TANK_IDS` | - | TANK-01,TANK-02,TANK-03 | 모니터링 수조 목록 |

> **CORS_ORIGINS 주의**: 브라우저는 포트 80을 생략하므로 `http://localhost:80`과 `http://localhost` 모두 추가해야 합니다.

---

## 15. 프로덕션 체크리스트

- [ ] `SECRET_KEY` 강력한 랜덤값 (`openssl rand -hex 32`)
- [ ] `JWT_REFRESH_SECRET_KEY` 별도 랜덤값
- [ ] `INTERNAL_API_KEY` / `BACKEND_API_KEY` 동일한 랜덤값으로 설정
- [ ] `REGISTRATION_OPEN=false` 확인
- [ ] `COOKIE_SECURE=true` (HTTPS 환경에서 필수)
- [ ] `POSTGRES_PASSWORD` 강력한 비밀번호로 변경
- [ ] `DEBUG=false` 확인
- [ ] `CORS_ORIGINS` 실제 도메인만 허용
- [ ] Nginx HTTPS 설정 (Let's Encrypt 또는 인증서)
- [ ] MLflow 외부 접근 차단 또는 인증 추가
- [ ] S3 버킷 및 접근 키 설정 (데이터 레이크)
- [ ] PostgreSQL 정기 백업 정책 수립
- [ ] K8s Secrets에 민감값 주입 (Sealed Secrets / External Secrets)
- [ ] HPA(수평 파드 오토스케일러) 임계값 검토

---

## 16. 구현 현황

- [x] **Phase 1**: 기본 인프라 — Docker Compose, FastAPI, PostgreSQL/TimescaleDB, Alembic, 헬스체크
- [x] **Phase 2**: AI 모듈 — YOLOv8 성장, ResNet18 급이, LSTM 수질 예측 + MLflow 연동
- [x] **Phase 3**: LangGraph 에이전트 + Redis 실시간 파이프라인 + JWT/쿠키 인증
- [x] **Phase 4**: MLOps 자동화 — AutoML, ONNX 엣지 배포, A/B 카나리, PSI 드리프트 감지
- [x] **Phase 5**: Kubernetes 매니페스트 (HPA·CronJob·Ingress·kustomize), GitHub Actions CI
- [x] **QA**: Docker 전체 스택 빌드·실행 검증, make migrate·seed 통과, 보안 버그 수정
- [x] **UI 개선**: 수질 전용 상세 페이지(`/water-quality`), 다크 모드 토글, Mock 데이터 모드, Recharts 기반 차트, Zustand 상태관리 추가

---

## 17. 알려진 이슈 및 해결 이력

### 해결된 이슈

| 증상 | 원인 | 해결책 |
|------|------|--------|
| `make migrate` 실패 (`DuplicateTableError`) | `init_db()`의 `create_all()`이 Alembic보다 먼저 테이블 생성 | `init_db()`에서 `create_all()` 제거, Alembic이 DDL 단독 관리 |
| 마이그레이션 멱등성 | 기존 테이블에 재실행 시 오류 | `information_schema` 조회로 조건부 생성, `if_not_exists=True` |
| 로그인 500 오류 | passlib 1.7.4 + bcrypt 4.x 비호환 | `security.py`를 `bcrypt` 직접 사용으로 교체 |
| 로그인 CORS 실패 | `CORS_ORIGINS`에 `http://localhost:80`만 있고 `http://localhost` 누락 | `.env`에 `http://localhost` 추가 |
| 대시보드 502 Bad Gateway | nginx upstream DNS 캐시 stale (frontend 재시작 후) | `resolver 127.0.0.11 valid=10s` + upstream 변수화 |
| `email-validator` 누락 | `pydantic` → `pydantic[email]` 미설정 | `backend/pyproject.toml` 수정 |
| agents `uvicorn` 없음 | `fastapi`, `uvicorn` 의존성 누락 | `agents/pyproject.toml` 추가 |
| MLflow 환경변수 미치환 | CMD 배열 형식은 셸 변수 치환 안 됨 | Dockerfile CMD를 셸 형식으로 변경 |
| nginx 헬스체크 실패 | busybox wget이 `localhost` → IPv6로 해석 | 헬스체크 URL을 `127.0.0.1`로 변경 |
| frontend nginx 시작 실패 | agents 미기동 시 upstream 미해석 | `resolver` + `set $upstream` 변수화 |
| WebSocket 비정상 종료 | `asyncio.FIRST_EXCEPTION` → Redis disconnect 미감지 | `asyncio.FIRST_COMPLETED`로 변경 |
| 대시보드 Redis 캐시 미동작 | `MonitoringService(db)` → redis 미주입 | `Depends(get_redis)` 추가 후 주입 |
| 에이전트 401 오류 | dashboard 라우터가 `get_current_user` 전용 | `require_auth_or_service`로 변경 |

### 현재 제한사항

- **실제 AI 모델 미탑재**: 모델 체크포인트 없이 실행 시 mock 값 반환 (정상 동작)
- **학습 데이터 필요**: `mlops/training/train_*.py` 실행하거나 합성 데이터 스크립트 활용
- **에이전트 반복 401**: `ANTHROPIC_API_KEY`·`INTERNAL_API_KEY` 미설정 시 에이전트 동작 제한

---

## 라이선스

MIT License © 2026 AIAquafarm Team
