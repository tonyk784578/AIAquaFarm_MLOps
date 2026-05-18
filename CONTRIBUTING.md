# Contributing to AIAquafarm

Thanks for taking the time. This document explains how to develop, test, and
ship changes to the platform.

> Operational incident response is in [`docs/runbook.md`](docs/runbook.md).
> Architecture overview is in [`docs/architecture.md`](docs/architecture.md).
> Codebase conventions are in [`CLAUDE.md`](CLAUDE.md).

---

## Repo layout

```
backend/       FastAPI REST + WebSocket API   (Python 3.11)
agents/        LangGraph orchestration         (Python 3.11)
ai_modules/    PyTorch models                  (Python 3.11)
mlops/         Registry / drift / AutoML       (Python 3.11)
frontend/      React + Vite + TS + Tailwind
edge/          On-device sensor + camera bridges
infra/         k8s manifests + Nginx + Prometheus configs
scripts/       Data generators + helper scripts
docs/          Architecture, API spec, runbook
```

The three Python service roots have **separate `pyproject.toml`** files —
import across roots only via HTTP, never as Python modules.

---

## Local development

### One-time setup

```bash
cp .env.example .env                     # fill SECRET_KEY, JWT_REFRESH_SECRET_KEY,
                                          # INTERNAL_API_KEY, ANTHROPIC_API_KEY
make build && make up
make migrate
make seed                                # seeds an admin user when REGISTRATION_OPEN=true
```

### Day-to-day

```bash
make dev                                 # backend with hot-reload
make logs-backend                        # tail logs
make test                                # pytest inside backend container
make codegen                             # regenerate frontend types from /openapi.json
make backup                              # local pg_dump snapshot
```

Frontend:

```bash
cd frontend
npm install
npm run dev                              # Vite dev server :3000, proxies to backend
npm test                                 # Vitest unit tests
npm run e2e                              # Playwright E2E (stack must be up)
```

### Useful helpers

| Task                              | Command                                          |
|-----------------------------------|--------------------------------------------------|
| Run one backend test              | `docker compose exec backend pytest tests/test_api.py::test_X -v` |
| Trigger an agent cycle manually   | `curl -X POST -H "X-Service-Key: $KEY" agents:8001/run` |
| Open Prometheus UI                | `make up` with `docker-compose.observability.yml` → `http://localhost:9090` |
| Inspect MLflow                    | `http://localhost:5000`                          |

---

## Branching + commit style

* `master` (main) is the deploy branch. Open PRs against it.
* Feature branches: `feature/<short-name>`, `fix/<issue>`, `chore/<scope>`.
* Commit messages: **imperative present**, ≤ 72 chars in the subject:
  ```
  add water-quality threshold to optimizer
  fix race in sensor publisher reconnect
  refactor agent runtime to share http client
  ```
* Conventional commit prefixes (`feat:`, `fix:`, `chore:`, `docs:`, `test:`) are
  welcome but not required.

---

## Quality gates

Every PR runs (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)):

| Job                | Time   | What                                                 |
|--------------------|--------|------------------------------------------------------|
| `lint`             | ~30 s  | `ruff check` on backend/agents/ai_modules/mlops      |
| `secret-scan`      | ~30 s  | gitleaks against `.gitleaks.toml`                    |
| `test-backend`     | ~3 min | pytest against postgres + redis service containers   |
| `test-mlops`       | ~30 s  | pytest on `mlops/tests/`                             |
| `test-agents`      | ~30 s  | pytest on `agents/tests/`                            |
| `test-frontend`    | ~1 min | Vitest + type-check                                  |
| `docker-build`     | ~3 min | (PRs only) builds backend/agents/frontend images     |

Local equivalents:

```bash
make lint                                  # ruff
make test                                  # backend
docker compose exec backend pytest tests/  # same
cd frontend && npm run type-check && npm test
```

PRs are blocked on any failure. Re-run a flaky check via the GitHub UI; do
not force-push to fix CI unless you have a reason.

---

## Writing changes

### Backend / Python

* Use `structlog`: `logger.info("event_name", k=v)`, not f-strings.
* Async functions everywhere in request paths — no blocking I/O.
* Validate user input at the API boundary with Pydantic; never interpolate
  into `text()` SQL.
* For AI inference: handle the unloaded-engine state, return mock/default
  values, never raise from a request path.
* New endpoints with cost/risk get a rate-limit decorator from
  [`backend/app/core/limiter.py`](backend/app/core/limiter.py).

### Frontend

* All cross-cutting calls go through [`src/services/api.ts`](frontend/src/services/api.ts).
* Server state: `@tanstack/react-query`. Client state: Zustand or local hook.
* Tailwind for layout; CSS variables (`var(--info)`, etc.) for theme colors.
* Don't add a top-level dependency without a corresponding `dist/` size check.
* Components that can throw should be wrapped — `<ErrorBoundary>` is at the
  router level but new pages should consider their own boundary.

### Infrastructure

* k8s manifests are kustomize-friendly; everything new gets a line in
  `infra/k8s/kustomization.yaml`.
* Secrets are never committed in plaintext. See
  [`infra/k8s/secrets/README.md`](infra/k8s/secrets/README.md) for the
  sealed-secrets / SOPS workflow.

---

## Testing checklist

Before opening a PR, mentally tick:

- [ ] Unit tests for new pure functions (Python: `pytest`, TS: Vitest).
- [ ] Integration test exercises the change in context if you added an endpoint.
- [ ] E2E spec updated if the user-visible flow changed.
- [ ] Logs say something useful when the change fails at runtime.
- [ ] No new `OBSERVABILITY_METRICS_ENABLED`-aware path skips metrics.
- [ ] `make codegen` re-run if the backend schema changed.

---

## Reporting bugs

Open a GitHub issue with:

1. **Repro** — exact steps, ideally a `curl` or short script.
2. **Expected vs actual** — one sentence each.
3. **Environment** — branch / commit, docker compose vs k8s, OS.
4. **Logs** — paste the most relevant 20-line block (use ``` fences).

For production incidents: also page the on-call channel and follow the
runbook. The issue is for the post-mortem, not the live response.

---

## License

The repo's [`LICENSE`](LICENSE) applies to all contributions. By submitting a
PR you agree your changes are licensed under the same terms.
