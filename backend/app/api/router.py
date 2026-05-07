"""Top-level API router — aggregates all versioned sub-routers."""

from fastapi import APIRouter

from app.api.v1 import alerts, control, dashboard, monitoring, water_quality_predict, ws_monitoring

api_router = APIRouter()

api_router.include_router(dashboard.router, prefix="/v1/dashboard", tags=["Dashboard"])
api_router.include_router(
    monitoring.router, prefix="/v1/monitoring", tags=["Monitoring"]
)
api_router.include_router(control.router, prefix="/v1/control", tags=["Control"])
api_router.include_router(alerts.router, prefix="/v1/alerts", tags=["Alerts"])
api_router.include_router(
    water_quality_predict.router,
    prefix="/v1/water-quality",
    tags=["Water Quality"],
)
api_router.include_router(
    ws_monitoring.router,
    prefix="/v1/ws",
    tags=["WebSocket"],
)
