# Load tests (k6)

Smoke + soak scripts for the public API surface. Three concerns are covered:

| Script               | Target                                      | What it stresses                          |
|----------------------|---------------------------------------------|-------------------------------------------|
| `dashboard.k6.js`    | `GET /api/v1/dashboard/summary`             | Backend REST + Postgres + Redis cache     |
| `monitoring-ws.k6.js`| `WS /api/v1/ws/monitoring/{tank_id}`        | WebSocket fan-out from Redis pub/sub      |
| `agents-sse.k6.js`   | `GET /agents/events/stream`                 | SSE keepalive + Redis subscriber capacity |

## Running

Install k6 once (https://k6.io/docs/get-started/installation/), then:

```bash
# Bring the stack up first
make up && make seed

# Smoke (low VU count, short)
k6 run load/dashboard.k6.js

# Soak (higher VUs, 5 min)
K6_VUS=50 K6_DURATION=5m k6 run load/dashboard.k6.js

# Override the base URL or admin credentials
K6_BASE_URL=http://prod-host k6 run \
    -e ADMIN_USER=admin -e ADMIN_PASS=secret \
    load/dashboard.k6.js
```

For CI: a Github Actions workflow can run smoke variants on `workflow_dispatch`.
Soak tests are intentionally NOT in CI — run them on a dedicated host.

## Thresholds

Every script enforces minimal SLOs via `thresholds`. If any breach, k6 exits
non-zero so the run can fail a pipeline:

- `http_req_failed`         < 1 %
- `http_req_duration{p(95)}` < 500 ms  (REST)
- `ws_session_duration`     custom — see script
- `checks`                  > 99 %

## Auth

The dashboard + SSE endpoints require a login cookie. Each script logs in via
`POST /api/v1/auth/login`, captures `aq_access`, and reuses it. The admin
credentials default to `admin`/`admin` (seeded by `make seed`); override via
the `-e ADMIN_USER=… -e ADMIN_PASS=…` flags.

## Interpreting results

```text
   data_received...: 12 MB  217 kB/s
   data_sent.......: 3.4 MB 61 kB/s
   http_req_duration.....: avg=45.2ms  p(95)=130.4ms
   http_req_failed.......: 0.00%   ✓ 0    ✗ 1842
   iterations............: 1842    33/s
   ws_connecting.........: avg=12ms
   ws_msgs_received......: 18 420   ← Redis fan-out throughput
```

p(95) > 500 ms on dashboard usually means the 5 s cache lapsed and every VU
hit Postgres concurrently. Increase the cache TTL (`monitoring_service.py`)
or add a CDN in front of the API.
