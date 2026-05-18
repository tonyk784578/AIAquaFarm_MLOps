"""Top-level API router — aggregates all versioned sub-routers."""

from fastapi import APIRouter, Depends

from app.api.deps import require_auth_or_service, require_superuser
from app.api.v1 import (
    admin,
    alerts,
    auth,
    control,
    dashboard,
    feeding_analyse,
    growth_detect,
    mlops,
    monitoring,
    settings,
    water_quality_predict,
    ws_monitoring,
)
from app.api.v1.auth import get_current_user

api_router = APIRouter()

# Public — no auth required
api_router.include_router(auth.router, prefix="/v1/auth", tags=["Authentication"])

# Superuser-only admin routes (require_superuser already wraps get_current_user)
api_router.include_router(
    admin.router,
    prefix="/v1/admin",
    tags=["Admin"],
    dependencies=[Depends(require_superuser)],
)

# Dashboard — browser users and internal agents both need aggregated summary
api_router.include_router(
    dashboard.router,
    prefix="/v1/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(require_auth_or_service)],
)
api_router.include_router(
    settings.router,
    prefix="/v1/settings",
    tags=["Settings"],
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    ws_monitoring.router,
    prefix="/v1/ws",
    tags=["WebSocket"],
    dependencies=[Depends(get_current_user)],
)

# Routes accessible to both browser users and internal agent service
api_router.include_router(
    monitoring.router,
    prefix="/v1/monitoring",
    tags=["Monitoring"],
    dependencies=[Depends(require_auth_or_service)],
)
api_router.include_router(
    control.router,
    prefix="/v1/control",
    tags=["Control"],
    dependencies=[Depends(require_auth_or_service)],
)
api_router.include_router(
    alerts.router,
    prefix="/v1/alerts",
    tags=["Alerts"],
    dependencies=[Depends(require_auth_or_service)],
)
api_router.include_router(
    water_quality_predict.router,
    prefix="/v1/water-quality",
    tags=["Water Quality AI"],
    dependencies=[Depends(require_auth_or_service)],
)
api_router.include_router(
    growth_detect.router,
    prefix="/v1/growth",
    tags=["Growth AI"],
    dependencies=[Depends(require_auth_or_service)],
)
api_router.include_router(
    feeding_analyse.router,
    prefix="/v1/feeding",
    tags=["Feeding AI"],
    dependencies=[Depends(require_auth_or_service)],
)
# MLOps proxy — read endpoints for browser users, write endpoints for superusers only
api_router.include_router(
    mlops.router,
    prefix="/v1/mlops",
    tags=["MLOps"],
    dependencies=[Depends(get_current_user)],
)
