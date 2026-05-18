# AIAquafarm API Specification

FastAPI 자동 생성 문서: `http://localhost:8000/api/docs`

---

## Base URL

```
http://localhost:8000/api/v1
```

Agent 서버 (LangGraph):

```
http://localhost:8001
```

---

## 인증

| 클라이언트 | 인증 방식 |
|-----------|-----------|
| 브라우저 | httpOnly 쿠키 `aq_access` (로그인 시 서버가 자동 설정) |
| API 클라이언트 | `Authorization: Bearer <token>` 헤더 |
| 내부 서비스 (에이전트) | `X-Service-Key: <INTERNAL_API_KEY>` 헤더 |

WebSocket 연결(`/api/v1/ws/monitoring/{tank_id}`)은 쿠키가 핸드셰이크 시 자동으로 전송되므로 별도 헤더 불필요.

---

## Endpoints

### Health Check

```
GET /health
→ { "status": "healthy", "service": "aquafarm-backend", "version": "0.1.0" }
```

---

### Authentication

#### POST /auth/login
로그인. 응답 바디에 토큰을 반환하고, httpOnly 쿠키(`aq_access`, `aq_refresh`)도 동시에 설정.
Rate limit: IP당 10회/분.

**Body** (`application/x-www-form-urlencoded`):
```
username=admin&password=secret
```

**Response**:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

#### POST /auth/refresh
토큰 갱신. `aq_refresh` 쿠키(브라우저) 또는 바디의 `refresh_token`을 수락.

**Body** (선택적):
```json
{ "refresh_token": "eyJ..." }
```

#### POST /auth/logout
httpOnly 쿠키 삭제.

#### GET /auth/me
현재 인증된 사용자 프로필 반환.

**Response**: `UserResponse`
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "full_name": "Admin",
  "is_active": true,
  "is_superuser": true
}
```

#### POST /auth/register
신규 사용자 등록. `REGISTRATION_OPEN=true` 환경변수 설정 시에만 활성화.

**Body**:
```json
{
  "username": "user1",
  "email": "user1@example.com",
  "password": "password123",
  "full_name": "User One"
}
```

---

### Dashboard

#### GET /dashboard/summary
대시보드 요약 스냅샷. Redis 5초 TTL 캐시 적용.

**Response**:
```json
{
  "water_quality": { "tank_id": "TANK-01", "ammonia_ppm": 0.3, "nitrite_ppm": 0.05, "..." },
  "fish_growth": { "tank_id": "TANK-01", "fish_count": 120, "biomass_kg": 48.5, "..." },
  "active_alert_count": 2,
  "recent_alerts": [ "...Alert[]" ]
}
```

#### GET /dashboard/tanks
모니터링 중인 수조 목록 (설정 기반).

**Response**:
```json
[
  { "tank_id": "TANK-01", "name": "1번 수조", "status": "online" },
  { "tank_id": "TANK-02", "name": "2번 수조", "status": "online" }
]
```

---

### Monitoring

#### GET /monitoring/water-quality/latest
최근 수질 데이터 조회.

**Query params**:
| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `tank_id` | str | — | 수조 필터 (선택) |
| `limit` | int | 10 | 최대 건수 (1–100) |

**Response**: `WaterQualityRead[]`

#### GET /monitoring/water-quality/history
수질 이력 — TimescaleDB `time_bucket()` 집계.

**Query params**:
| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `tank_id` | str | (필수) | 수조 ID |
| `start_time` | datetime | — | 범위 시작 (ISO 8601) |
| `end_time` | datetime | — | 범위 종료 (ISO 8601) |
| `bucket_minutes` | int | 60 | 집계 버킷 너비(분), 1–1440 |
| `limit` | int | 100 | 최대 버킷 수 (1–1000) |

**Response**: `list[dict]` — 각 버킷별 평균값
```json
[
  {
    "bucket": "2024-01-15T10:00:00",
    "temperature_c": 23.5,
    "ph": 7.2,
    "dissolved_oxygen_mgl": 7.8,
    "ammonia_ppm": 0.28,
    "nitrite_ppm": 0.04,
    "sample_count": 12
  }
]
```

#### GET /monitoring/fish-growth/latest
최근 어류 성장 데이터.

**Query params**: `tank_id?: str`, `limit?: int (1-100, default 10)`

**Response**: `FishGrowthRead[]`

#### GET /monitoring/feeding/latest
최근 급이 기록.

**Query params**: `tank_id?: str`, `limit?: int (1-100, default 20)`

**Response**: `FeedingRead[]`

---

### Alerts

#### GET /alerts/
알림 목록.

**Query params**: `tank_id?: str`, `active_only?: bool (default true)`, `limit?: int (default 50)`

**Response**: `AlertRead[]`

#### POST /alerts/
알림 생성 (AI 에이전트 또는 시스템 내부 호출).

**Body**:
```json
{
  "tank_id": "TANK-01",
  "severity": "warning",
  "category": "water_quality",
  "title": "암모니아 경고",
  "message": "암모니아 농도 0.5 ppm 초과",
  "source": "management_agent"
}
```

**Severity**: `critical` | `warning` | `info`

#### PATCH /alerts/{alert_id}/resolve
알림 해결 처리.

**Body**:
```json
{ "resolution_notes": "수동 환수 실시", "resolved_by": "admin" }
```

---

### Control

모든 컨트롤 엔드포인트는 Redis `cmd:{tank_id}:{device}` 채널에 명령을 publish하고 202 Accepted를 즉시 반환합니다.

`tank_id` 형식: `^[A-Z0-9][A-Z0-9_\-]*$` (예: `TANK-01`, `T01A`)

#### POST /control/feeding/trigger
급이 명령 발송.

**Body**:
```json
{
  "tank_id": "TANK-01",
  "amount_kg": 2.5,
  "duration_s": 120
}
```

**Response**: `{ "job_id": "uuid", "status": "accepted", "tank_id": "TANK-01", "amount_kg": 2.5, "channel": "cmd:TANK-01:feeder", "dispatched_at": "..." }`

#### POST /control/feeding/stop/{tank_id}
급이 긴급 정지.

**Response**: `{ "job_id": "uuid", "status": "stop_accepted" }`

#### POST /control/feeding/adjust
다음 급이량 조정.

**Body**: `{ "tank_id": "TANK-01", "reduction_factor": 0.7 }` (0.0 = 중단, 1.0 = 변경 없음)

#### POST /control/pump/{tank_id}/{action}
순환 펌프 제어. `action`: `start` | `stop`

#### POST /control/aeration/increase
폭기 블로어 강도 증가.

**Body**: `{ "tank_id": "TANK-01", "boost_pct": 30.0 }` (기본 30%)

#### POST /control/water-exchange
부분 환수 트리거.

**Body**: `{ "tank_id": "TANK-01", "exchange_pct": 10.0 }` (기본 10%, 최대 50%)

---

### Water Quality AI

#### GET /water-quality/predict
가상 센서 + LSTM 모델로 수질 예측.

**Query params**: `tank_id: str`

**Response**: `WaterQualityPrediction`

#### GET /water-quality/status
수질 AI 모델 로드 상태 확인.

---

### Growth AI

#### GET /growth/count/{tank_id}
어류 카운트 및 생체량 추정.

**Response**:
```json
{
  "tank_id": "TANK-01",
  "fish_count": 120,
  "avg_length_cm": 28.5,
  "avg_weight_g": 412.0,
  "biomass_kg": 49.4
}
```

#### GET /growth/status
성장 AI 모델 로드 상태 확인.

---

### Feeding AI

#### GET /feeding/status
급이 활성도 분석 및 급이량 추천.

**Response**:
```json
{
  "activity_score": 0.72,
  "satiation_detected": false,
  "recommended_amount_kg": 2.1
}
```

#### GET /feeding/model-status
급이 AI 모델 로드 상태 확인.

---

### WebSocket

#### WS /ws/monitoring/{tank_id}
실시간 수질 + 알림 스트림.

`tank_id` 형식: `^[A-Z0-9][A-Z0-9_\-]*$` 또는 `ALL` (전체 수조). 형식 위반 시 코드 1008로 즉시 종료.

구독 채널:
- `wq:{tank_id}` — 수질 데이터 (5초마다)
- `events:alerts` — 신규 알림 이벤트

**수신 메시지 형식**:
```json
{ "type": "water_quality", "tank_id": "TANK-01", "timestamp": "2024-01-15T10:30:00Z", "data": { "..." } }
{ "type": "alert",         "tank_id": "TANK-01", "timestamp": "2024-01-15T10:30:05Z", "data": { "..." } }
{ "type": "ping" }
```

서버는 30초마다 `{"type": "ping"}` 전송 (데드 커넥션 감지용).

---

### Agents (LangGraph, port 8001)

`/run` 과 `/optimize` 는 `X-Service-Key` 헤더가 필수입니다 (`require_service_key`). 그 외 조회 엔드포인트는 사내 네트워크 내에서 인증 없이 접근 가능합니다.

#### GET /health
에이전트 서버 헬스체크. 응답에 `management_graph` 가용성, `redis_connected`, `event_channel`, `tanks`, `cycle_interval_s`, `version` 포함.

#### POST /run
전체 관리 사이클 실행 (데이터 수집 → AI 분석 → 제어 명령 → 보고서). `X-Service-Key` 필수.

**Query**: `tank_id=ALL` (기본값) — 다중 탱크 모드에서는 스케줄러가 자동으로 `DEFAULT_TANK_IDS` 순회.

**Response**:
```json
{
  "status": "ok",
  "tank_id": "ALL",
  "final_report": "Management cycle #1 complete. Actions taken: ...",
  "decisions": 3,
  "executed": 2
}
```

#### POST /optimize
최적화 서브그래프만 단독 실행 (AI 모듈 수집 → 후보 생성 → 디지털 트윈 → 최적 선택). `X-Service-Key` 필수.

**Body**:
```json
{
  "tank_id": "TANK-01",
  "ammonia_ppm": 0.4,
  "nitrite_ppm": 0.08,
  "dissolved_oxygen_mgl": 7.0,
  "temperature_c": 23.0,
  "water_exchange_rate_pct": 5.0
}
```

#### GET /status

가장 최근 관리 사이클 결과 (Redis 영속화).

#### GET /optimization/status?tank_id=TANK-01

탱크별 최근 최적화 결과. `tank_id` 미지정 시 전체 최근 1건 반환.

#### GET /history?n=20

최근 관리 사이클 N개 이력 (Redis LIST). 최대 200.

#### GET /history/optimization?n=20

최근 최적화 사이클 N개 이력.

#### GET /events/stream

**Server-Sent Events** — 에이전트 노드 진행 + 결정 + 명령 실행 이벤트 라이브 스트림. 응답 헤더 `Content-Type: text/event-stream`.

각 이벤트는 `event: agent\ndata: <json>` 또는 `event: ping\ndata:` (keepalive). JSON 페이로드:

```json
{
  "ts": "2026-05-18T10:00:00+00:00",
  "kind": "node_completed",
  "tank_id": "TANK-01",
  "data": { "node": "analyse_situation", "duration_ms": 4210 }
}
```

이벤트 종류: `cycle_started`, `cycle_completed`, `node_started`, `node_completed`, `decision_made`, `command_executed`, `command_failed`, `optimization_started`, `optimization_completed`, `error`.

브라우저는 `/agents/events/stream` 경로로 nginx 를 통해 접근 (`useEventSource` 훅).

---

### MLOps API (proxied at /api/v1/mlops/*)

브라우저는 백엔드 프록시를 통해 호출 (쿠키 인증). 백엔드가 자동으로 `X-Service-Key` 를 주입해 `mlops_api:8002` 로 포워딩.

#### GET /api/v1/mlops/registry

MLflow 등록 모델 전체 목록 + Stage 별 버전.

**Response**:
```json
{
  "models": [
    {
      "name": "WaterQualityPredictor",
      "production_version": "12",
      "staging_version": "13",
      "versions": [
        {"name": "WaterQualityPredictor", "version": "12", "stage": "Production", "run_id": "abc123..."}
      ]
    }
  ]
}
```

회로차단기 + 30초 캐시 폴백 적용 — MLflow 다운 시 마지막 스냅샷 반환 (응답은 동일 형태).

#### GET /api/v1/mlops/audit?n=50&kind=automl&model=WaterQualityPredictor

MLOps 감사 로그 조회. `kind` 필터: `automl` | `drift` | `promotion` | `rollback` | `deployment` | `training` | `error`. `n` 1–1000.

**Response**:
```json
{
  "events": [
    {
      "ts": "2026-05-18T10:00:00+00:00",
      "kind": "drift",
      "model": "WaterQualityPredictor",
      "data": {
        "max_psi": 0.234,
        "should_retrain": true,
        "features": [{"feature": "ammonia_ppm", "psi": 0.31, "status": "drift"}]
      }
    }
  ],
  "count": 1
}
```

#### GET /api/v1/mlops/drift

모델별 최신 드리프트 리포트 (감사 로그 `latest("drift")` 기반).

#### POST /api/v1/mlops/retrain

**Superuser only.** 단일 모델 재훈련 사이클 트리거. Rate limit: 10/분.

**Body**:
```json
{ "model": "WaterQualityPredictor", "dry_run": true }
```

#### POST /api/v1/mlops/promote

**Superuser only.** 특정 MLflow run 을 Production 으로 승격. Rate limit: 10/분.

**Body**:
```json
{ "model": "WaterQualityPredictor", "run_id": "abc123...", "force": false }
```

#### POST /api/v1/mlops/deploy

**Superuser only.** Production 모델을 엣지 디바이스에 배포 (ONNX export → SCP → smoke test → 실패 시 롤백). Rate limit: 10/분.

**Body**:
```json
{ "model": "WaterQualityPredictor" }
```

`model: null` 또는 누락 시 전체 모델 배포.

---

## Schema Definitions

### WaterQualityRead

| Field | Type | Description |
|-------|------|-------------|
| id | int | PK |
| tank_id | str | 수조 ID (`TANK-01` 형식) |
| measured_at | datetime | 측정 시각 (UTC) |
| temperature_c | float? | 수온 (°C) |
| ph | float? | pH |
| dissolved_oxygen_mgl | float? | 용존산소 (mg/L) |
| turbidity_ntu | float? | 탁도 (NTU) |
| ammonia_ppm | float? | 암모니아 (ppm, 가상센서 예측) |
| nitrite_ppm | float? | 아질산 (ppm, 가상센서 예측) |
| ammonia_confidence | float? | 암모니아 예측 신뢰도 (0–1) |
| nitrite_confidence | float? | 아질산 예측 신뢰도 (0–1) |
| source | str | `sensor` \| `virtual_sensor` \| `manual` |

### Alert Severity

| Level | 조건 예시 |
|-------|-----------|
| `critical` | 즉시 조치 — 암모니아 ≥ 1.0 ppm, DO < 5.0 mg/L |
| `warning` | 주의 — 암모니아 ≥ 0.5 ppm, 아질산 ≥ 0.1 ppm |
| `info` | 참고 정보 |

### Alert Category

`water_quality` | `feeding` | `growth` | `system`

---

## Error Responses

| HTTP Status | 설명 |
|-------------|------|
| 401 | 인증 토큰 없음 또는 만료 (또는 잘못된 `X-Service-Key`) |
| 403 | 권한 없음 (슈퍼유저 전용 또는 등록 비활성) |
| 404 | 리소스 없음 |
| 409 | 중복 (username/email 이미 존재) |
| 413 | 요청 본문 크기 초과 (기본 1 MiB; `MAX_REQUEST_BYTES` 로 조정) |
| 422 | 입력 유효성 오류 |
| 429 | Rate limit 초과 |
| 501 | sse-starlette 미설치 (에이전트 `/events/stream` 한정) |
| 503 | Redis 연결 실패 (제어 명령) 또는 mlops_api → MLflow 회로차단기 OPEN + 캐시 없음 |

```json
{ "detail": "Alert 123 not found" }
{ "detail": [{ "loc": ["body", "tank_id"], "msg": "string does not match regex" }] }
{ "detail": "request body too large", "max_bytes": 1048576, "observed_bytes": 1234567 }
```

**Rate limit 헤더**: 429 응답에는 slowapi 가 `Retry-After` 헤더를 첨부합니다. `is_internal_service` 가 `X-Service-Key` 일치를 확인하면 `/control/*`, `/alerts/` 엔드포인트는 슬로어피를 우회합니다.
