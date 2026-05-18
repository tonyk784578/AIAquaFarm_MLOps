"""Cross-cutting observability for the agents service — see also
``backend/app/observability.py`` and ``mlops/observability.py``.

Identical pattern, scoped to the agents service. Both Prometheus metrics
and OpenTelemetry tracing are best-effort: missing optional deps degrade
to no-op so the service still boots.

Usage::

    from agents.observability import setup_observability
    setup_observability(app, service_name="aquafarm-agents")
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def setup_prometheus(app: Any, service_name: str) -> bool:
    if os.getenv("OBSERVABILITY_METRICS_ENABLED", "true").lower() == "false":
        return False
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        logger.warning("prometheus_instrumentator_not_installed")
        return False

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health"],
    )
    instrumentator.instrument(app, metric_namespace=service_name.replace("-", "_"))
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("prometheus_metrics_attached service=%s", service_name)
    return True


def setup_tracing(service_name: str, app: Any | None = None) -> bool:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
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
        logger.warning("opentelemetry_sdk_not_installed")
        return False

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("SERVICE_VERSION", "0.2.0"),
            "deployment.environment": os.getenv("DEPLOY_ENV", "dev"),
        }
    )
    provider = TracerProvider(resource=resource)
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() != "false"
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure)))
    trace.set_tracer_provider(provider)

    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/metrics")
        except Exception as exc:
            logger.warning("otel_fastapi_failed: %s", exc)

    # httpx (outbound to backend), redis (state store / event bus)
    for mod_path, cls_name in (
        ("opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor"),
        ("opentelemetry.instrumentation.redis", "RedisInstrumentor"),
    ):
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            getattr(mod, cls_name)().instrument()
        except Exception:
            pass

    logger.info("otel_tracing_attached service=%s endpoint=%s", service_name, endpoint)
    return True


def setup_observability(app: Any, service_name: str) -> dict[str, bool]:
    return {
        "metrics": setup_prometheus(app, service_name),
        "tracing": setup_tracing(service_name, app=app),
    }
