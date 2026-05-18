"""Cross-cutting observability — Prometheus metrics + OpenTelemetry tracing.

Both subsystems are opt-in:

* **Prometheus metrics** auto-attach if `prometheus_fastapi_instrumentator` is
  installed. Disable with ``OBSERVABILITY_METRICS_ENABLED=false``. Exposes
  ``GET /metrics`` and tags series with ``service=aquafarm-backend``.

* **OpenTelemetry tracing** is enabled only when
  ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (e.g. ``http://otel-collector:4317``).
  Auto-instruments FastAPI, httpx, SQLAlchemy, and redis-py.

Both helpers degrade silently when their optional dependency is missing, so
the service still boots in a minimal dev image.

Single entry point::

    from app.observability import setup_observability
    setup_observability(app, service_name="aquafarm-backend")
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def setup_prometheus(app: Any, service_name: str) -> bool:
    """Attach Prometheus metrics + /metrics endpoint to a FastAPI app.

    Args:
        app: FastAPI application.
        service_name: Value of the ``service`` label on every metric.

    Returns:
        True if metrics were attached, False if disabled or library missing.
    """
    if os.getenv("OBSERVABILITY_METRICS_ENABLED", "true").lower() == "false":
        logger.info("observability_metrics_disabled_via_env")
        return False

    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        logger.warning("prometheus_instrumentator_not_installed_skipping_metrics")
        return False

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health"],
    )
    instrumentator.instrument(app, metric_namespace=service_name.replace("-", "_"))
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("prometheus_metrics_attached", extra={"service": service_name})
    return True


def setup_tracing(service_name: str, app: Any | None = None) -> bool:
    """Configure OpenTelemetry tracing with an OTLP exporter.

    No-op when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset. This keeps dev/test
    runs free of network calls to a tracing backend.

    Args:
        service_name: ``service.name`` resource attribute.
        app: Optional FastAPI app to auto-instrument.

    Returns:
        True if tracing was wired up, False otherwise.
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.debug("otel_endpoint_unset_tracing_disabled")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("opentelemetry_sdk_not_installed_skipping_tracing")
        return False

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
            "deployment.environment": os.getenv("DEPLOY_ENV", "dev"),
        }
    )
    provider = TracerProvider(resource=resource)
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() != "false"
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrumentation — each is best-effort
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/metrics")
        except Exception as exc:
            logger.warning("otel_fastapi_instrumentation_failed", extra={"error": str(exc)})

    for module_name, instrumentor_path in (
        ("httpx", "opentelemetry.instrumentation.httpx:HTTPXClientInstrumentor"),
        ("sqlalchemy", "opentelemetry.instrumentation.sqlalchemy:SQLAlchemyInstrumentor"),
        ("redis", "opentelemetry.instrumentation.redis:RedisInstrumentor"),
    ):
        try:
            mod_path, cls_name = instrumentor_path.split(":")
            mod = __import__(mod_path, fromlist=[cls_name])
            getattr(mod, cls_name)().instrument()
        except Exception:
            # silently skip — instrumentor missing or target lib not in this service
            pass

    logger.info("otel_tracing_attached", extra={"service": service_name, "endpoint": endpoint})
    return True


def setup_observability(app: Any, service_name: str) -> dict[str, bool]:
    """Convenience wrapper: enable both subsystems and return their status.

    Args:
        app: FastAPI application.
        service_name: Logical service identifier.

    Returns:
        Dict ``{"metrics": bool, "tracing": bool}`` indicating what was wired up.
    """
    return {
        "metrics": setup_prometheus(app, service_name),
        "tracing": setup_tracing(service_name, app=app),
    }
