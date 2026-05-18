# AIAquafarm Operations Runbook

Incident-response playbooks for the live stack. Each section follows the same
shape: **Symptoms → Detect → Diagnose → Remediate → Verify**. Times in this
document are wall-clock estimates assuming a single operator with shell access
to the cluster.

> If you are paged and unsure which section applies, jump to
> [§ Triage decision tree](#triage-decision-tree).

---

## Service map (cheat sheet)

| Service          | Port  | Health endpoint            | Critical deps                          |
|------------------|-------|----------------------------|----------------------------------------|
| backend          | 8000  | `GET /health`              | postgres, redis, mlflow, ai_modules    |
| agents           | 8001  | `GET /health`              | backend, redis (state + events)        |
| mlops_api        | 8002  | `GET /health`              | mlflow, audit log (PVC)                |
| mlops_scheduler  | —     | logs only                  | mlflow, S3 data lake                   |
| mlflow           | 5000  | `GET /health`              | postgres                               |
| postgres         | 5432  | `pg_isready`               | volume                                 |
| redis            | 6379  | `redis-cli ping`           | volume                                 |
| nginx            | 80    | `GET /health`              | backend, frontend                      |

Internal-service traffic uses the `X-Service-Key` header; rate limiting on
`/control/*` and `/alerts/` exempts it. See [`backend/app/core/limiter.py`](../backend/app/core/limiter.py).

---

## Triage decision tree

```
Alert / user report
  └─ Dashboard blank or 500?            → § 1   Frontend white screen
  └─ Logins failing?                    → § 2   Auth outage
  └─ Real-time tile (water quality) stuck?
        └─ WebSocket disconnects?       → § 3   Realtime pipeline stalled
  └─ /agents page "no cycle yet" hours? → § 4   Agent scheduler stuck
  └─ /mlops registry empty / stale?     → § 5   MLflow unreachable
  └─ Retrain triggered but no promotion → § 6   AutoML / quality gate
  └─ DB error 500s, pg_isready fails    → § 7   Postgres incident
  └─ Need to restore from backup        → § 8   Postgres restore
  └─ Disk full warnings                 → § 9   Volume cleanup
```

---

## § 1 — Frontend white screen

**Symptoms.** User sees blank page or a "페이지 표시 중 오류" fallback (the
[ErrorBoundary](../frontend/src/components/ErrorBoundary.tsx) fired).

**Detect.**
```bash
make logs-frontend | tail -50
# Nginx access log on the gateway:
docker compose logs nginx | tail -50
```
If the ErrorBoundary rendered, the page itself is reachable — the bug is in
client code. If you get HTTP 502 instead, jump to **§ 7** (backend / nginx).

**Diagnose.** In browser DevTools, open the console and look for the line
prefixed `[ErrorBoundary]`. The first line of the stack trace points at the
broken component.

**Remediate.**
1. Identify the latest deploy: `git log -- frontend/src/ | head`.
2. Roll back the image: `docker compose up -d frontend --force-recreate`
   pointing at the previous tag, or re-deploy a fix.
3. If only one route is broken, the user can still use the rest of the app
   (the inner per-route boundary contains the damage).

**Verify.** Refresh; the boundary's "다시 시도" button calls `reset()` and
the route should re-mount cleanly.

---

## § 2 — Auth outage

**Symptoms.** All users see 401 on `/v1/auth/me`, or login attempts hang.

**Detect.**
```bash
make logs-backend | grep -E 'auth|login|jwt' | tail -30
make health     # backend /health should still be green
```

**Common causes.**
- `SECRET_KEY` or `JWT_REFRESH_SECRET_KEY` rotated without invalidating active
  sessions ⇒ every refresh fails. Users must log in again, which works.
- Postgres unreachable ⇒ login lookup fails. Check **§ 7**.
- Login rate limit (10/min/IP) firing if a bot is hammering credentials.

**Remediate.**
- If users are unable to log in *and* you just changed the secret, do not
  rotate again — let users log in fresh.
- If you suspect brute-force: check nginx access log, then `iptables` or the
  cloud WAF.

**Verify.** Send a `POST /api/v1/auth/login` with a known credential and
confirm a `Set-Cookie: aq_access=...` is returned.

---

## § 3 — Realtime pipeline stalled (no live water-quality updates)

**Symptoms.** Dashboard last-update timestamp grows past `SENSOR_POLL_INTERVAL`
(default 5 s). WebSocket icon shows disconnected.

**Detect.**
```bash
# Confirm SensorPublisher is alive
make logs-backend | grep -E 'sensor_publisher|wq:' | tail -20

# Verify Redis fan-out
docker compose exec redis redis-cli psubscribe 'wq:*'   # Ctrl-C after a few seconds
```

**Diagnose.**
| Observation                       | Likely cause                            |
|-----------------------------------|------------------------------------------|
| No `wq:*` messages on PSUBSCRIBE  | SensorPublisher crashed → restart backend |
| Redis OK but WS clients reconnect | Backend WS handler exception            |
| Backend logs show `redis_disconnect` | Redis container restarted             |

**Remediate.**
- `docker compose restart backend` (SensorPublisher re-spawns in lifespan).
- If Redis is the culprit: `docker compose restart redis` then backend.

**Verify.** Refresh the dashboard, click into one tank — fresh values within
2 × `SENSOR_POLL_INTERVAL`.

---

## § 4 — Agent scheduler stuck (no recent cycles)

**Symptoms.** `/agents` page shows "no_cycle_run_yet" for hours, or the
history timeline is empty / very stale.

**Detect.**
```bash
make logs-agents | grep -E 'management_cycle|scheduler' | tail -30
```

**Common causes.**
- `ANTHROPIC_API_KEY` missing / invalid → LLM call exhausts retries → cycle
  errors. Logs show `retry_llm_exhausted`. Rule-based fallback should still
  produce a no-op cycle.
- Backend reachable but `/api/v1/dashboard/summary` returns 503 →
  `collect_farm_data` writes `error` and the cycle short-circuits. Check
  postgres (§ 7).
- Redis down → state store falls back to in-memory; history disappears on
  restart. Logs show `redis_unavailable_degraded`.

**Remediate.**
- Trigger a manual cycle: from `/agents` page click **수동 실행**, or
  `POST /agents/run` with `X-Service-Key`.
- Roll the agents container: `docker compose restart agents`.

**Verify.** `GET /agents/health` returns `management_graph: true` and within
the next interval the `/agents/status` shows a fresh `ran_at`.

---

## § 5 — MLflow unreachable (mlops_api degraded)

**Symptoms.** `/mlops` registry panel says "MLOps 서비스에 연결할 수 없습니다"
or shows a stale snapshot.

**Detect.**
```bash
docker compose ps mlflow
docker compose exec mlflow curl -sf http://localhost:5000/health
make logs-mlflow | tail -50          # alembic / db connection issues?

# Circuit breaker state in mlops_api logs
docker compose logs mlops_api | grep -E 'circuit_(open|half_open|closed)|fallback' | tail
```

**Behaviour.** The circuit breaker
([`mlops/api/resilience.py`](../mlops/api/resilience.py)) opens after 5
consecutive failures and stays open for 30 s. While open, the API serves the
last cached response (`30 s` TTL but stale fallback is unbounded). After
recovery_seconds it goes HALF_OPEN and tries one live call.

**Remediate.**
- Verify postgres health (§ 7) — MLflow uses postgres as its backend store.
- `docker compose restart mlflow`. The breaker recovers automatically once
  calls succeed.
- If outage extends beyond the cache TTL → consumers see HTTP 503.

**Verify.** `curl localhost:8002/registry` returns fresh data and no
`circuit_open` lines appear in subsequent logs.

---

## § 6 — AutoML triggered but no promotion

**Symptoms.** Audit log shows `automl` events with `triggered: true` but no
`promotion` follow-up; same model stays at the old Production version.

**Detect.**
```bash
# Read the audit log directly
docker compose exec mlops_scheduler tail -50 /data/audit/automl.jsonl

# Or via the API
curl -s localhost:8002/audit?n=20 | jq '.events[] | {ts, kind, model, data: .data.gate_results}'
```

**Diagnose.** Inspect the `gate_results` field on the latest `automl` event:
- If a gate metric is `false` ⇒ candidate failed the quality gate. Expected
  behaviour; investigate training data or hyperparams.
- If `better_than_prod: false` ⇒ candidate passed but did not beat the
  incumbent. Tweak `force=true` on `POST /mlops/promote` if you accept the
  trade-off.

**Remediate.**
```bash
# Re-run from a specific MLflow run_id (superuser only)
curl -X POST localhost:8000/api/v1/mlops/promote \
     -b 'aq_access=...' \
     -d '{"model":"WaterQualityPredictor","run_id":"<run_id>","force":false}'
```

---

## § 7 — Postgres incident

**Symptoms.** Backend 500s, `pg_isready` fails, alerts stop being written.

**Detect.**
```bash
docker compose exec postgres pg_isready -U aquafarm -d aquafarm
make logs-backend | grep -E 'asyncpg|sqlalchemy' | tail
docker compose logs postgres | tail -50
```

**Remediate.**
- Disk full? Run `make logs` and look for `No space left on device`. See § 9.
- Crash loop? Inspect `docker compose logs postgres` for FATAL lines.
  Common: corrupted WAL → restore from the most recent backup (§ 8).
- Connection saturation: backend pool exhausted. Increase
  `SQLALCHEMY_POOL_SIZE` or scale backend pods.

**Verify.** `pg_isready` returns 0 and `curl /api/v1/dashboard/summary` is 2xx.

---

## § 8 — Postgres restore from backup

The nightly CronJob
([`infra/k8s/postgres/backup-cronjob.yaml`](../infra/k8s/postgres/backup-cronjob.yaml))
writes `pg_dump --format=custom` files to
`s3://{bucket}/backups/postgres/{db}/{ISO_TS}.dump`.

```bash
# 1. List recent backups
aws --endpoint-url "$S3_ENDPOINT_URL" s3 ls "s3://$S3_BUCKET_NAME/backups/postgres/aquafarm/" \
    | sort -r | head

# 2. Download
aws --endpoint-url "$S3_ENDPOINT_URL" s3 cp \
    "s3://$S3_BUCKET_NAME/backups/postgres/aquafarm/2026-05-17T03-00-00Z.dump" /tmp/

# 3. Restore into a freshly created database (do NOT pg_restore into the live one
#    while services are up — stop the backend first).
docker compose stop backend agents mlops_api mlops_scheduler
docker compose exec postgres bash -c '
    dropdb -U aquafarm aquafarm_restore || true;
    createdb -U aquafarm aquafarm_restore;
'
docker compose exec -T postgres pg_restore -U aquafarm --clean --if-exists \
    --no-owner --no-privileges -d aquafarm_restore < /tmp/aquafarm-2026-05-17.dump

# 4. Cut over: rename databases
docker compose exec postgres psql -U aquafarm -d postgres <<'SQL'
    ALTER DATABASE aquafarm        RENAME TO aquafarm_broken;
    ALTER DATABASE aquafarm_restore RENAME TO aquafarm;
SQL

# 5. Start the apps
docker compose start backend agents mlops_api mlops_scheduler
```

A manual on-demand dump (for migration safety) is one command: `make backup`.

**Verify.** Log in to the dashboard and confirm a recent alert / sensor row
is present.

---

## § 9 — Volume cleanup

Volumes that fill the host disk:

| Volume               | What                            | Safe action                                |
|----------------------|----------------------------------|--------------------------------------------|
| `postgres_data`      | DB + WAL                        | Vacuum, archive old hypertable chunks       |
| `mlflow_artifacts`   | Model checkpoints, params       | Delete archived runs from MLflow UI         |
| `redis_data`         | Pubsub + ephemeral history      | Restart Redis (data is non-critical)        |
| `mlops_data`         | Audit log + AutoML artefacts    | Audit log auto-rotates at 8 MiB             |
| `prometheus_data`    | Metrics TSDB                    | Drop retention via `--storage.tsdb.retention.time` |

For `mlflow_artifacts` specifically: delete the `Archived` lifecycle stage
runs from the UI, then run `mlflow gc --backend-store-uri ...` inside the
mlflow container.

---

## Routine: emergency stop all feeders

If a tank is in critical state and you cannot reach the UI:

```bash
# Pick the tank ID
TANK=TANK-01
curl -X POST -H "X-Service-Key: $INTERNAL_API_KEY" \
     "http://backend:8000/api/v1/control/feeding/stop/$TANK"
```

The agent will see the stop in its next cycle and won't override it unless a
human dismisses the resulting alert.

---

## Routine: rotate the internal service key

1. Generate a new key: `openssl rand -hex 32`.
2. Update the secret (k8s) or `.env` (compose).
3. Roll services **in order**: backend → agents → mlops_api. Each picks up
   the new key on restart; cross-service calls fail in the gap.
4. Verify: `curl -H 'X-Service-Key: <new>' /api/v1/dashboard/summary` returns 2xx.

---

## On-call checklist

Before logging off, confirm:

- [ ] All services healthy: `make health`
- [ ] No `error` events in the last 100 audit-log entries
- [ ] `/agents/health` returns `redis_connected: true`
- [ ] Backup ran in the last 24 h: `aws s3 ls .../backups/postgres/aquafarm/ | tail`
- [ ] Disk usage below 75% on the postgres + mlflow volumes
