"""AIAquafarm FastAPI application entry point.

Configures CORS, mounts API routers, registers lifecycle hooks,
and exposes the health-check endpoint used by Docker orchestration.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import get_settings
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

    # Load water quality inference engine (best-effort; degraded mode if MLflow unreachable)
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

    yield
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
