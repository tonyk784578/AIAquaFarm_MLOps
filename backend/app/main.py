"""AIAquafarm FastAPI application entry point.

Configures CORS, mounts API routers, registers lifecycle hooks,
and exposes the health-check endpoint used by Docker orchestration.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.core.limiter import limiter
from app.db.session import init_db

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle.

    Runs DB initialization on startup and performs graceful cleanup on shutdown.

    Args:
        app: The FastAPI application instance.

    Yields:
        Control to the application while running.
    """
    logger.info("starting_aquafarm_backend", version="0.1.0", env=settings.log_level)
    await init_db()
    logger.info("database_initialized")

    # ── Redis connection ─────────────────────────────────────────────────────
    from app.db.redis import close_redis, init_redis
    try:
        await init_redis(settings.redis_url)
    except Exception as exc:
        logger.warning("redis_init_failed", error=str(exc), msg="Control commands will fail")

    # ── Water quality inference engine ──────────────────────────────────────
    from app.services.water_quality_service import WaterQualityInferenceEngine

    if settings.wq_checkpoint_path:
        app.state.wq_engine = WaterQualityInferenceEngine.from_checkpoint(
            settings.wq_checkpoint_path,
            settings.wq_scaler_path,
            device=settings.wq_model_device,
        )
    else:
        app.state.wq_engine = WaterQualityInferenceEngine.from_mlflow(
            tracking_uri=settings.mlflow_tracking_uri,
            model_name=settings.wq_model_name,
            stage=settings.wq_model_stage,
            device=settings.wq_model_device,
        )

    # ── Growth inference engine ──────────────────────────────────────────────
    from app.services.growth_service import GrowthInferenceEngine

    if settings.growth_checkpoint_path:
        app.state.growth_engine = GrowthInferenceEngine.from_checkpoint(
            settings.growth_checkpoint_path,
        )
    else:
        app.state.growth_engine = GrowthInferenceEngine.from_mlflow(
            tracking_uri=settings.mlflow_tracking_uri,
            model_name=settings.growth_model_name,
            stage=settings.growth_model_stage,
        )

    # ── Feeding inference engine ─────────────────────────────────────────────
    from app.services.feeding_service import FeedingInferenceEngine

    if settings.feeding_checkpoint_path:
        app.state.feeding_engine = FeedingInferenceEngine.from_checkpoint(
            settings.feeding_checkpoint_path,
        )
    else:
        app.state.feeding_engine = FeedingInferenceEngine.from_mlflow(
            tracking_uri=settings.mlflow_tracking_uri,
            model_name=settings.feeding_model_name,
            stage=settings.feeding_model_stage,
        )

    # ── Sensor publisher (virtual sensor → Redis + PostgreSQL) ────────────────
    from app.db.redis import get_redis_client
    from app.db.session import AsyncSessionLocal
    from app.services.sensor_publisher import SensorPublisher

    try:
        redis_client = get_redis_client()
        tank_ids = settings.default_tank_ids
        publisher = SensorPublisher(
            tank_ids=tank_ids,
            poll_interval=settings.sensor_poll_interval,
            redis=redis_client,
            session_factory=AsyncSessionLocal,
            # Write to DB every 6 ticks (≈ 30 s at 5 s interval)
            db_write_every=max(1, 30 // max(1, settings.sensor_poll_interval)),
        )
        publisher.start()
        app.state.sensor_publisher = publisher
        logger.info("sensor_publisher_started", tanks=tank_ids)
    except Exception as exc:
        logger.warning("sensor_publisher_init_failed", error=str(exc))
        app.state.sensor_publisher = None

    yield

    if getattr(app.state, "sensor_publisher", None):
        await app.state.sensor_publisher.stop()
    await close_redis()
    logger.info("shutting_down_aquafarm_backend")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Fully configured FastAPI application instance.
    """
    app = FastAPI(
        title="AIAquafarm API",
        description=(
            "AI-powered RAS smart aquaculture platform.\n\n"
            "Provides real-time monitoring, AI-driven control, and MLOps management "
            "for recirculating aquaculture systems."
        ),
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Service-Key"],
    )

    app.include_router(api_router, prefix="/api")

    @app.get("/health", tags=["Health"], summary="Service health check")
    async def health_check() -> JSONResponse:
        """Health check endpoint for container orchestration and load balancers.

        Returns:
            JSON with service status, name, and version.
        """
        return JSONResponse(
            content={
                "status": "healthy",
                "service": "aquafarm-backend",
                "version": "0.1.0",
            }
        )

    return app


app = create_app()
