"""Backend → MLOps service proxy.

The MLOps FastAPI runs on its own container (``mlops_api:8002``) and
authenticates write requests with ``X-Service-Key``. Browser clients use
cookies and can't see that key, so the backend acts as a forwarding proxy:

* Read endpoints (``GET``) are forwarded as-is.
* Write endpoints (``POST``) are forwarded with the service key injected
  from the backend's own ``INTERNAL_API_KEY`` setting.

Routes:
    GET  /api/v1/mlops/registry
    GET  /api/v1/mlops/audit
    GET  /api/v1/mlops/drift
    POST /api/v1/mlops/retrain   (superuser only)
    POST /api/v1/mlops/promote   (superuser only)
    POST /api/v1/mlops/deploy    (superuser only)
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import require_superuser
from app.config import Settings, get_settings
from app.core.limiter import LIMIT_MLOPS_ADMIN, limiter

logger = structlog.get_logger()

router = APIRouter()

_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)


async def _proxy_get(
    settings: Settings, path: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Forward a GET request to the MLOps service."""
    url = f"{settings.mlops_api_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        logger.error("mlops_proxy_unavailable", url=url, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MLOps service unavailable: {exc}",
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def _proxy_post(
    settings: Settings, path: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Forward a POST request to the MLOps service, injecting the service key."""
    if not settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_API_KEY not configured — cannot reach MLOps service",
        )
    url = f"{settings.mlops_api_url.rstrip('/')}{path}"
    headers = {"X-Service-Key": settings.internal_api_key}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        logger.error("mlops_proxy_unavailable", url=url, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MLOps service unavailable: {exc}",
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# ── Read endpoints (forwarded as-is) ───────────────────────────────────────────


@router.get("/registry")
async def get_registry(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """List all registered models, their versions, and stages."""
    return await _proxy_get(settings, "/registry")


@router.get("/audit")
async def get_audit(
    n: int = Query(default=50, ge=1, le=1000),
    kind: str | None = Query(default=None),
    model: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return the most recent MLOps audit-log events."""
    params: dict[str, Any] = {"n": n}
    if kind:
        params["kind"] = kind
    if model:
        params["model"] = model
    return await _proxy_get(settings, "/audit", params=params)


@router.get("/drift")
async def get_drift(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Return the latest drift report per registered model."""
    return await _proxy_get(settings, "/drift")


# ── Admin endpoints (superuser only) ──────────────────────────────────────────


@router.post("/retrain", dependencies=[Depends(require_superuser)])
@limiter.limit(LIMIT_MLOPS_ADMIN)
async def trigger_retrain(
    request: Request, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Manually trigger a retraining cycle for one model. Superuser only."""
    body = await request.json()
    return await _proxy_post(settings, "/retrain", body=body)


@router.post("/promote", dependencies=[Depends(require_superuser)])
@limiter.limit(LIMIT_MLOPS_ADMIN)
async def trigger_promote(
    request: Request, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Promote a specific MLflow run to Production. Superuser only."""
    body = await request.json()
    return await _proxy_post(settings, "/promote", body=body)


@router.post("/deploy", dependencies=[Depends(require_superuser)])
@limiter.limit(LIMIT_MLOPS_ADMIN)
async def trigger_deploy(
    request: Request, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Push production models to the edge device. Superuser only."""
    body = await request.json()
    return await _proxy_post(settings, "/deploy", body=body)
