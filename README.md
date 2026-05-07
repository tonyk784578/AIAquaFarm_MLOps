# AIAquafarm — AI 기반 스마트 RAS 양식장 플랫폼

RAS(순환여과식) 양식장을 위한 AI 통합 관리 플랫폼입니다.
비전 AI, 시계열 예측, LangGraph 멀티에이전트, MLOps 파이프라인을 결합하여
수질 관리·어류 성장·먹이 급이를 완전 자동화합니다.

---

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                    통합 대시보드 (React/TypeScript)               │
│        모니터링 · 알림 · 제어 인터페이스 · 설정 관리              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST API / WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│               FastAPI 백엔드 (Python 3.11)                       │
│    /api/v1/dashboard · monitoring · control · alerts             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│            통합 관리 에이전트 (LangGraph)                         │
│         멀티 에이전트 오케스트레이션 · 의사결정 워크플로우          │
└──────┬──────────────────────────────────────────┬───────────────┘
       │                                          │
┌──────▼──────────┐                   ┌───────────▼───────────────┐
│  최적화 에이전트  │                   │     RASbit 디지털 트윈     │
│  (LangGraph)    │                   │  물리 모델 시뮬레이션       │
└──────┬──────────┘                   └───────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                      AI 모듈 (RASbit Core)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  성장관리 AI  │  │  먹이효율 AI  │  │     수질관리 AI       │  │
│  │  비전 모델    │  │  비전 모델    │  │  시계열 예측 모델      │  │
│  │  사이즈 측정  │  │  활성도 분석  │  │  암모니아/아질산 예측  │  │
│  │  어류 카운트  │  │  급이량 최적화 │  │  가상센서             │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    MLOps 파이프라인                               │
│  Edge Device → Data Collector → Data Lake → Training Pipeline   │
│  → Model Registry (MLflow) → CI/CD → Edge Deployment            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│               인프라 (PostgreSQL/TimescaleDB · Redis)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 기술 스택

| 계층 | 기술 |
|------|------|
| Frontend | React 18, TypeScript, Vite, TailwindCSS |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| AI 에이전트 | LangGraph, LangChain, Anthropic Claude |
| AI 모델 | PyTorch, Ultralytics YOLO, TimesNet/LSTM |
| MLOps | MLflow, Alembic |
| 데이터베이스 | PostgreSQL 15 + TimescaleDB |
| 캐시/브로커 | Redis 7 |
| 컨테이너 | Docker, Docker Compose |
| 코드 품질 | ruff, mypy, pytest, structlog |

---

## 빠른 시작

### 사전 요구사항
- Docker >= 24.0
- Docker Compose >= 2.20
- GNU Make

### 1. 환경 설정

```bash
cp .env.example .env
# .env 파일에서 SECRET_KEY, ANTHROPIC_API_KEY 등 필수 값 설정
```

### 2. 서비스 시작

```bash
# 전체 서비스 빌드 및 시작
make build
make up

# 또는 개발 모드 (hot-reload)
make dev
```

### 3. DB 마이그레이션

```bash
make migrate
```

### 4. 테스트 데이터 시드

```bash
make seed
```

### 5. 접속

| 서비스 | URL |
|--------|-----|
| 대시보드 | http://localhost |
| API Docs (Swagger) | http://localhost:8000/api/docs |
| MLflow UI | http://localhost:5000 |
| API ReDoc | http://localhost:8000/api/redoc |

---

## 개발 명령어

```bash
make help          # 전체 명령어 목록
make logs          # 전체 로그 확인
make logs-backend  # 백엔드 로그만 확인
make test          # 테스트 실행
make lint          # 린터 실행
make format        # 코드 포맷팅
make health        # 서비스 헬스체크
```

---

## 프로젝트 구조

```
AIAquafarm/
├── backend/          FastAPI 백엔드 서버
├── agents/           LangGraph AI 에이전트
├── ai_modules/       RASbit 핵심 AI 모듈 (성장·먹이·수질)
├── mlops/            데이터 수집·학습·배포 파이프라인
├── frontend/         React 대시보드
├── edge/             엣지 디바이스 (카메라·센서)
├── infra/            인프라 설정 (Nginx·PostgreSQL·Redis·MLflow)
├── docs/             프로젝트 문서
└── scripts/          유틸리티 스크립트
```

---

## 구현 로드맵

- [x] **Phase 1**: 기본 인프라 — Docker, FastAPI, DB, 헬스체크
- [ ] **Phase 2**: AI 모듈 — 성장·먹이·수질 모델 구현
- [ ] **Phase 3**: LangGraph 에이전트 — 멀티에이전트 오케스트레이션
- [ ] **Phase 4**: MLOps 파이프라인 — 데이터 수집·학습·배포 자동화
- [ ] **Phase 5**: 프론트엔드 — 실시간 대시보드 완성

---

## 라이선스

MIT License © 2025 AIAquafarm Team
