import logging
import os
import sys
from typing import Optional

import structlog
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_fastapi_instrumentator import Instrumentator


def configure_structured_logging(service: str, env: str) -> structlog.stdlib.BoundLogger:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger(service=service, env=env)


def configure_tracing(service: str, env: str) -> TracerProvider:
    resource = Resource.create(
        {
            "service.name": service,
            "deployment.environment": env,
        }
    )
    provider = TracerProvider(resource=resource)
    running_pytest = (
        "pytest" in sys.modules
        or any("pytest" in arg for arg in sys.argv)
        or bool(os.getenv("PYTEST_CURRENT_TEST"))
    )
    if not running_pytest:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider


def setup_observability(app, service: str = "fastapi-backend", env: str = "local"):
    logger = configure_structured_logging(service=service, env=env)
    provider = configure_tracing(service=service, env=env)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    return logger


def current_trace_id() -> Optional[str]:
    span = trace.get_current_span()
    span_context = span.get_span_context()
    if not span_context or not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")
