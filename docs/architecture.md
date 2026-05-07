# AIAquafarm 아키텍처 문서

## 시스템 개요

AIAquafarm은 RAS(순환여과식) 양식장을 위한 AI 통합 관리 플랫폼입니다.
5개 계층으로 구성된 멀티레이어 아키텍처를 채용합니다.

---

## 계층별 설계

### Layer 1 — 통합 대시보드 (Frontend)

**기술**: React 18 + TypeScript + Vite + TailwindCSS

**책임**:
- 실시간 수질/성장/급이 모니터링 UI
- 알림 수신 및 해결 인터페이스
- 장비 원격 제어 패널
- WebSocket 기반 실시간 데이터 수신 (Phase 2)

**통신**:
- REST API (`/api/v1/*`) → FastAPI 백엔드
- WebSocket (`/ws/*`) → 실시간 이벤트 스트림 (Phase 2)

---

### Layer 2 — FastAPI 백엔드

**기술**: FastAPI + SQLAlchemy (async) + PostgreSQL/TimescaleDB + Redis

**책임**:
- REST API 엔드포인트 노출
- 인증/인가 (Phase 4)
- DB 읽기/쓰기 (water_quality, fish_growth, feeding, alerts)
- Redis pub/sub 제어 명령 디스패치

**주요 엔드포인트**:
```
GET  /api/v1/dashboard/summary      — 대시보드 스냅샷
GET  /api/v1/monitoring/water-quality/latest
GET  /api/v1/monitoring/water-quality/history
GET  /api/v1/monitoring/fish-growth/latest
GET  /api/v1/alerts/
POST /api/v1/alerts/
POST /api/v1/control/feeding/trigger
POST /api/v1/control/feeding/stop/{tank_id}
```

---

### Layer 3 — 통합 관리 에이전트 (LangGraph)

**기술**: LangGraph + LangChain + Anthropic Claude

**책임**:
- 하위 최적화 에이전트 조율
- 농장 전체 의사결정 워크플로우
- 자연어 설명 보고서 생성

**그래프 노드**:
```
collect_data → analyse_situation → [anomaly?] → execute_commands
                                  → [normal]  → generate_report
```

---

### Layer 4 — 최적화 에이전트 (LangGraph Subgraph)

**기술**: LangGraph + RASbit Digital Twin API

**책임**:
- 3개 AI 모듈 출력 종합
- 제어 액션 후보 생성
- 디지털 트윈 시뮬레이션 검증
- 최적 제어 명령 선택

**그래프 노드**:
```
gather_module_outputs → generate_candidates → simulate_in_twin → select_optimal
```

---

### Layer 5 — RASbit AI 모듈

#### 성장관리 AI (`ai_modules/growth/`)
- **입력**: 카메라 프레임 (JPEG)
- **모델**: YOLOv8 fish detection
- **출력**: fish_count, avg_length_cm, avg_weight_g, biomass_kg

#### 먹이효율 AI (`ai_modules/feeding/`)
- **입력**: 카메라 프레임 (급이 기간)
- **모델**: ResNet-based activity classifier
- **출력**: activity_score (0-1), recommended_amount_kg

#### 수질관리 AI (`ai_modules/water_quality/`)
- **입력**: 24시간 물리 센서 시계열 (온도, pH, DO, 탁도)
- **모델**: LSTM/TimesNet (seq2seq)
- **출력**: ammonia_ppm, nitrite_ppm, confidence scores

---

### Layer 6 — MLOps 파이프라인

```
Edge Device
    │
    ├── Camera → CameraCollector → Data Lake (S3/MinIO) → CVAT Labeling
    │                                                          │
    │                                              Training Pipeline (MLflow)
    │                                                          │
    └── Sensor → SensorCollector ──────→ PostgreSQL/TimescaleDB
                      │
                      └── VirtualSensor (실시간 AI 추론)
```

**MLflow 등록 모델**:
- `FishDetection` — YOLOv8 fish detection
- `FeedingActivityClassifier` — 급이 활성도 분류
- `WaterQualityPredictor` — 수질 예측 LSTM

---

## 데이터 흐름

### 실시간 모니터링 흐름
```
Physical Sensor
    → SensorCollector (5s interval)
    → POST /api/v1/monitoring/water-quality
    → WaterQualityReading (TimescaleDB hypertable)
    → VirtualSensor.update()
    → ammonia/nitrite prediction
    → [threshold breach?] → Alert created
    → Redis pub/sub → WebSocket → Frontend
```

### AI 제어 흐름 (Phase 3 대상)
```
ManagementAgent.run()
    → collect_farm_data()    : GET /api/v1/dashboard/summary
    → analyse_situation()    : LLM analysis
    → OptimizationAgent.run()
        → gather_module_outputs()
        → generate_candidates() : LLM candidate generation
        → simulate_in_twin()    : RASbit Digital Twin API
        → select_optimal()
    → execute_commands()     : POST /api/v1/control/*
```

---

## 데이터베이스 스키마

### TimescaleDB Hypertables
- `water_quality_readings` — partitioned by `measured_at` (daily chunks)
- `fish_growth_records` — partitioned by `measured_at` (weekly chunks)
- `feeding_records` — partitioned by `started_at` (weekly chunks)

### Regular Tables
- `alerts` — 알림 레코드 (active_alert 인덱스)

---

## 보안 설계

- 모든 시크릿은 환경변수 (하드코딩 금지)
- JWT 기반 API 인증 (Phase 4)
- Redis pub/sub 채널은 내부 네트워크 전용
- Nginx가 외부 트래픽 종단점

---

## 확장성 고려사항

- TimescaleDB hypertable을 통한 시계열 데이터 수평 확장
- FastAPI async/await 비동기 처리
- MLflow를 통한 모델 버전 관리 및 무중단 배포
- Docker Compose → Kubernetes 마이그레이션 경로 (Phase 5)
