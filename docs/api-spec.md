# AIAquafarm API Specification

FastAPI 자동 생성 문서: `http://localhost:8000/api/docs`

---

## Base URL

```
http://localhost:8000/api/v1
```

---

## Endpoints

### Health Check
```
GET /health
→ { "status": "healthy", "service": "aquafarm-backend", "version": "0.1.0" }
```

---

### Dashboard

#### GET /dashboard/summary
대시보드 요약 스냅샷

**Response**:
```json
{
  "water_quality": { ... WaterQualityRead },
  "fish_growth": { ... FishGrowthRead },
  "active_alert_count": 2,
  "recent_alerts": [ ... Alert[] ]
}
```

#### GET /dashboard/tanks
수조 목록

**Response**: `[{ "tank_id": "T001", "name": "1번 수조", "status": "online" }]`

---

### Monitoring

#### GET /monitoring/water-quality/latest
최근 수질 데이터

**Query params**: `tank_id?: str`, `limit?: int (1-100, default 10)`

**Response**: `WaterQualityRead[]`

#### GET /monitoring/water-quality/history
수질 이력 조회

**Query params**: `tank_id: str`, `start_time?: datetime`, `end_time?: datetime`, `limit?: int`

**Response**: `WaterQualityRead[]`

#### GET /monitoring/fish-growth/latest
최근 어류 성장 데이터

**Query params**: `tank_id?: str`, `limit?: int`

**Response**: `FishGrowthRead[]`

---

### Alerts

#### GET /alerts/
알림 목록

**Query params**: `tank_id?: str`, `active_only?: bool (default true)`, `limit?: int`

**Response**: `Alert[]`

#### POST /alerts/
알림 생성 (AI 모듈 내부 호출)

**Body**: `AlertCreate`
```json
{
  "tank_id": "T001",
  "severity": "warning",
  "category": "water_quality",
  "title": "암모니아 경고",
  "message": "암모니아 농도 0.5 ppm 초과"
}
```

#### PATCH /alerts/{alert_id}/resolve
알림 해결 처리

**Body**: `AlertUpdate`
```json
{ "resolution_notes": "수동 환수 실시" }
```

---

### Control

#### POST /control/feeding/trigger
급이 명령 발송

**Body**: `FeedingCommand`
```json
{
  "tank_id": "T001",
  "amount_kg": 2.5,
  "duration_seconds": 120
}
```

**Response**: `{ "job_id": "uuid", "status": "accepted", "dispatched_at": "..." }`

#### POST /control/feeding/stop/{tank_id}
급이 긴급 정지

**Response**: `{ "job_id": "uuid", "status": "stop_accepted" }`

#### POST /control/pump/{tank_id}/{action}
펌프 제어 (`action`: `start` | `stop`)

---

## Schema Definitions

### WaterQualityRead
| Field | Type | Description |
|-------|------|-------------|
| id | int | PK |
| tank_id | str | 수조 ID |
| measured_at | datetime | 측정 시각 |
| temperature_c | float? | 수온 (°C) |
| ph | float? | pH |
| dissolved_oxygen_mgl | float? | 용존산소 (mg/L) |
| turbidity_ntu | float? | 탁도 (NTU) |
| ammonia_ppm | float? | 암모니아 (ppm, 가상센서) |
| nitrite_ppm | float? | 아질산 (ppm, 가상센서) |
| source | str | sensor \| virtual_sensor \| manual |

### Alert Severity Levels
| Level | Condition |
|-------|-----------|
| critical | 즉시 조치 필요 (암모니아 ≥ 1.0 ppm, DO < 5.0 mg/L) |
| warning | 주의 필요 (암모니아 ≥ 0.5 ppm) |
| info | 참고 정보 |

---

## Error Responses

```json
{ "detail": "Alert 123 not found" }  // 404
{ "detail": [{ "loc": [...], "msg": "..." }] }  // 422 Validation
```
