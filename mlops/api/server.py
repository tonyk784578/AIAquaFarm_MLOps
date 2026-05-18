"""FastAPI app exposing MLOps observability and admin endpoints.

Endpoints
---------
    GET  /health                       — liveness + summary counters
    GET  /registry                     — registered models + versions + stages
    GET  /audit?n=&kind=&model=        — recent audit log entries
    GET  /drift                        — latest drift reports per model
    POST /retrain   (service-key)      — manually trigger a single-model retrain
    POST /promote   (service-key)      — promote a specific run to Production
    POST /deploy    (service-key)      — push production models to the edge

Write endpoints require the ``X-Service-Key`` header to match
``Settings.internal_api_key``.

The backend FastAPI app (port 8000) proxies the read endpoints under
``/api/v1/mlops/*`` and adds the service-key header for the write endpoints,
so end users authenticate via the normal cookie flow and never see the
service key.
"""

from __future__ import annotations

from typing import Any

import asyncio

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware

from mlops.api.resilience import CircuitOpenError, call_with_fallback

from mlops.api.schemas import (
    ActionResponse,
    AuditEntry,
    AuditResponse,
    DeployRequest,
    DriftFeature,
    DriftReport,
    DriftResponse,
    HealthResponse,
    ModelVersionInfo,
    PromoteRequest,
    RegisteredModel,
    RegistryResponse,
    RetrainRequest,
)
from mlops.config import Settings, get_settings
from mlops.evaluation.evaluator import ModelEvaluator
from mlops.orchestrator.audit_log import AuditLog
from mlops.registry.mlflow_registry import REGISTERED_MODELS, ModelRegistry

logger = structlog.get_logger()

# ── Dependencies ───────────────────────────────────────────────────────────────


def get_audit_log(settings: Settings = Depends(get_settings)) -> AuditLog:
    return AuditLog(settings.audit_log_path)


def get_registry(settings: Settings = Depends(get_settings)) -> ModelRegistry:
    return ModelRegistry(settings.mlflow_tracking_uri)


def get_evaluator(settings: Settings = Depends(get_settings)) -> ModelEvaluator:
    return ModelEvaluator(tracking_uri=settings.mlflow_tracking_uri)


def require_service_key(
    settings: Settings = Depends(get_settings),
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
) -> None:
    """Reject write requests without a valid service key."""
    if not x_service_key or x_service_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Service-Key",
        )


# ── App factory ────────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build the MLOps FastAPI application."""
    app = FastAPI(
        title="AIAquafarm MLOps API",
        version="0.1.0",
        description="Read-only MLOps observability + service-gated admin actions.",
    )

    # Restrict CORS: the MLOps API is only reachable from the backend service
    # inside the cluster network. Browser clients reach it through
    # /api/v1/mlops/* on the backend, which uses server-to-server httpx (no
    # browser CORS involved). The only legitimate browser origin is for
    # local dev/Swagger; opt-in via MLOPS_CORS_ORIGINS.
    settings_for_cors = get_settings()
    cors_origins = [
        o.strip()
        for o in (settings_for_cors.cors_origins or "").split(",")
        if o.strip()
    ]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["X-Service-Key", "Content-Type"],
            allow_credentials=False,
        )

    # ── Observability (Prometheus metrics + OpenTelemetry tracing) ──
    from mlops.observability import setup_observability

    setup_observability(app, service_name="aquafarm-mlops-api")

    # ── Resilience: circuit breaker + cached fallback for MLflow calls ──
    from mlops.api.resilience import CircuitBreaker, ResponseCache

    app.state.mlflow_breaker = CircuitBreaker(
        name="mlflow", failure_threshold=5, recovery_seconds=30.0
    )
    app.state.mlflow_cache = ResponseCache(ttl_seconds=30.0)

    # ── HTTP hardening ──────────────────────────────────────────────────
    from mlops.api.security import (
        RequestSizeLimitMiddleware,
        SecurityHeadersMiddleware,
    )

    app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=1 * 1024 * 1024)
    app.add_middleware(SecurityHeadersMiddleware)

    # ── Health ─────────────────────────────────────────────────────────────────

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    def health(
        settings: Settings = Depends(get_settings),
        audit: AuditLog = Depends(get_audit_log),
    ) -> HealthResponse:
        return HealthResponse(
            status="ok",
            mlflow_uri=settings.mlflow_tracking_uri,
            audit_log_path=str(settings.audit_log_path),
            audit_events=len(audit.tail(n=10_000)),
        )

    # ── Registry ───────────────────────────────────────────────────────────────

    def _build_registry(registry: ModelRegistry) -> RegistryResponse:
        out: list[RegisteredModel] = []
        for model_name in REGISTERED_MODELS:
            versions_raw = registry.list_model_versions(model_name)
            prod = next((v["version"] for v in versions_raw if v["stage"] == "Production"), None)
            staging = next((v["version"] for v in versions_raw if v["stage"] == "Staging"), None)
            out.append(
                RegisteredModel(
                    name=model_name,
                    production_version=prod,
                    staging_version=staging,
                    versions=[ModelVersionInfo(**v) for v in versions_raw],
                )
            )
        return RegistryResponse(models=out)

    @app.get("/registry", response_model=RegistryResponse, tags=["observability"])
    async def list_registry(
        request: Request,
        registry: ModelRegistry = Depends(get_registry),
    ) -> RegistryResponse:
        """Live MLflow registry — circuit-broken, with cached fallback when MLflow is down."""
        breaker = request.app.state.mlflow_breaker
        cache = request.app.state.mlflow_cache

        async def _fetch() -> RegistryResponse:
            # MLflow client is sync — run in a worker thread to avoid blocking the loop.
            return await asyncio.to_thread(_build_registry, registry)

        try:
            value, was_fallback = await call_with_fallback(
                breaker=breaker, cache=cache, key="registry", func=_fetch
            )
        except CircuitOpenError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            )
        if was_fallback:
            logger.warning("registry_served_from_cache")
        return value

    # ── Audit log ──────────────────────────────────────────────────────────────

    @app.get("/audit", response_model=AuditResponse, tags=["observability"])
    def list_audit(
        n: int = Query(default=50, ge=1, le=1000),
        kind: str | None = Query(default=None),
        model: str | None = Query(default=None),
        audit: AuditLog = Depends(get_audit_log),
    ) -> AuditResponse:
        events = audit.tail(n=n, kind=kind, model=model)  # type: ignore[arg-type]
        return AuditResponse(
            events=[
                AuditEntry(ts=e.ts, kind=e.kind, model=e.model, data=e.data)
                for e in events
            ],
            count=len(events),
        )

    # ── Drift (latest) ─────────────────────────────────────────────────────────

    @app.get("/drift", response_model=DriftResponse, tags=["observability"])
    def latest_drift(audit: AuditLog = Depends(get_audit_log)) -> DriftResponse:
        reports: dict[str, DriftReport] = {}
        for model_name in REGISTERED_MODELS:
            latest = audit.latest("drift", model=model_name)
            if latest is None:
                continue
            d = latest.data
            reports[model_name] = DriftReport(
                model_name=d.get("model_name", model_name),
                max_psi=float(d.get("max_psi", 0.0)),
                mean_psi=float(d.get("mean_psi", 0.0)),
                should_retrain=bool(d.get("should_retrain", False)),
                n_reference=int(d.get("n_reference", 0)),
                n_current=int(d.get("n_current", 0)),
                features=[DriftFeature(**f) for f in d.get("features", [])],
            )
        return DriftResponse(reports=reports)

    # ── Admin: trigger retraining ──────────────────────────────────────────────

    @app.post(
        "/retrain",
        response_model=ActionResponse,
        dependencies=[Depends(require_service_key)],
        tags=["admin"],
    )
    def trigger_retrain(
        req: RetrainRequest,
        settings: Settings = Depends(get_settings),
        audit: AuditLog = Depends(get_audit_log),
    ) -> ActionResponse:
        if req.model not in REGISTERED_MODELS:
            raise HTTPException(status_code=400, detail=f"unknown model '{req.model}'")
        # Defer the heavy work to the scheduler — fire-and-forget by writing
        # an audit event the next AutoML cycle can detect, or run inline if
        # the caller is OK to wait. Here we run inline (one model) to keep
        # the API simple; for long-running training jobs use the scheduler.
        from mlops.orchestrator.scheduler import OrchestratorScheduler

        scheduler = OrchestratorScheduler(settings=settings, audit=audit)
        # Reuse the pipeline's internal single-model helper for the requested
        # one by short-circuiting through check_and_retrain with only one path.
        kwargs: dict[str, Any] = {"dry_run": req.dry_run}
        if req.model == "WaterQualityPredictor":
            kwargs["water_data_path"] = settings.wq_training_csv
        elif req.model == "FeedingActivityClassifier":
            kwargs["feeding_data_path"] = settings.feeding_training_dir
        elif req.model == "FishDetection":
            kwargs["growth_data_yaml"] = settings.growth_training_yaml

        result = scheduler.pipeline.check_and_retrain(**kwargs)
        per_model = result["results"].get(req.model, {})
        audit.log("training", model=req.model, data={"manual": True, **per_model})
        return ActionResponse(
            ok=True,
            detail=f"retrain cycle complete for {req.model}",
            data=per_model,
        )

    # ── Admin: promote a run ───────────────────────────────────────────────────

    @app.post(
        "/promote",
        response_model=ActionResponse,
        dependencies=[Depends(require_service_key)],
        tags=["admin"],
    )
    def promote_run(
        req: PromoteRequest,
        evaluator: ModelEvaluator = Depends(get_evaluator),
        audit: AuditLog = Depends(get_audit_log),
    ) -> ActionResponse:
        if req.model not in REGISTERED_MODELS:
            raise HTTPException(status_code=400, detail=f"unknown model '{req.model}'")
        result = evaluator.evaluate_and_maybe_promote(req.model, req.run_id, force=req.force)
        audit.log(
            "promotion" if result.get("promoted") else "error",
            model=req.model,
            data={"manual": True, **result},
        )
        return ActionResponse(
            ok=bool(result.get("promoted")),
            detail=result.get("message", ""),
            data=result,
        )

    # ── Admin: edge deployment ─────────────────────────────────────────────────

    @app.post(
        "/deploy",
        response_model=ActionResponse,
        dependencies=[Depends(require_service_key)],
        tags=["admin"],
    )
    def deploy_to_edge(
        req: DeployRequest,
        settings: Settings = Depends(get_settings),
        registry: ModelRegistry = Depends(get_registry),
        audit: AuditLog = Depends(get_audit_log),
    ) -> ActionResponse:
        if not settings.edge_host:
            raise HTTPException(
                status_code=400, detail="edge deployment is not configured (MLOPS_EDGE_HOST unset)",
            )
        from mlops.deployment.edge_deployer import EdgeDeployer

        deployer = EdgeDeployer(
            registry=registry,
            edge_host=settings.edge_host,
            edge_user=settings.edge_user,
            ssh_key_path=settings.edge_ssh_key,
            deploy_path=settings.edge_deploy_path,
            dry_run=settings.dry_run,
        )
        if req.model:
            if req.model not in REGISTERED_MODELS:
                raise HTTPException(status_code=400, detail=f"unknown model '{req.model}'")
            result = deployer.deploy_model(req.model).to_dict()
            audit.log("deployment", model=req.model, data=result)
            return ActionResponse(
                ok=bool(result.get("success")),
                detail=result.get("error") or "deployed",
                data=result,
            )

        result = deployer.deploy_all()
        for model_name, r in result.get("results", {}).items():
            audit.log("deployment", model=model_name, data=r)
        return ActionResponse(
            ok=result["summary"]["failed"] == 0,
            detail=f"{result['summary']['succeeded']}/{result['summary']['total']} deployed",
            data=result,
        )

    return app


app = create_app()
