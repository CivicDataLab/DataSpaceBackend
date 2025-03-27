"""Initialize OpenTelemetry instrumentation."""

import os
from typing import Any, Optional

from django.conf import settings
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.elasticsearch import ElasticsearchInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def setup_telemetry(service_name: Optional[str] = None) -> trace.Tracer:
    """Initialize OpenTelemetry with all required instrumentations.

    Args:
        service_name: Optional override for service name.
                     If not provided, uses OTEL_SERVICE_NAME from settings.

    Returns:
        A tracer instance for manual instrumentation.
    """
    # Use provided service name or get from settings
    service_name = service_name or settings.OTEL_SERVICE_NAME

    # Create resource with service information
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": settings.OTEL_RESOURCE_ATTRIBUTES["service.namespace"],
            "deployment.environment": settings.OTEL_RESOURCE_ATTRIBUTES[
                "deployment.environment"
            ],
        }
    )

    # Set up trace exporter
    otlp_trace_exporter = OTLPSpanExporter(
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        insecure=True,  # TODO: Configure with proper TLS in production
    )

    # Create and configure TracerProvider
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))

    # Add console exporter in development for debugging
    if settings.DEBUG:
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Set up metrics exporter
    otlp_metric_exporter = OTLPMetricExporter(
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        insecure=True,  # TODO: Configure with proper TLS in production
    )

    # Create and configure MeterProvider
    metric_reader = PeriodicExportingMetricReader(
        exporter=otlp_metric_exporter,
        export_interval_millis=settings.OTEL_METRIC_EXPORT_INTERVAL_MILLIS,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])

    # Set global meter provider
    metrics.set_meter_provider(meter_provider)

    # Initialize instrumentors if enabled in settings
    if getattr(settings, "OTEL_PYTHON_DJANGO_INSTRUMENT", True):
        DjangoInstrumentor().instrument(
            request_hook=lambda span, request: _add_request_attributes(span, request),
            response_hook=lambda span, response: _add_response_attributes(
                span, response
            ),
        )

    # Initialize additional instrumentors
    _initialize_instrumentors()

    # Create and return tracer for manual instrumentation
    return trace.get_tracer(__name__)


def _add_request_attributes(span: trace.Span, request: Any) -> None:
    """Add request attributes to span."""
    if not hasattr(request, "headers"):
        return

    # Add request headers as span attributes
    span.set_attribute("http.request.headers", str(dict(request.headers)))

    # Add user information if available
    if hasattr(request, "user") and request.user.is_authenticated:
        span.set_attribute("enduser.id", str(request.user.id))
        span.set_attribute("enduser.role", str(request.user.role))


def _add_response_attributes(span: trace.Span, response: Any) -> None:
    """Add response attributes to span."""
    if not hasattr(response, "headers"):
        return

    # Add response headers and status
    span.set_attribute("http.response.headers", str(dict(response.headers)))
    if hasattr(response, "status_code"):
        span.set_attribute("http.status_code", response.status_code)


def _initialize_instrumentors() -> None:
    """Initialize additional OpenTelemetry instrumentors."""
    # Import and apply the Elasticsearch instrumentation patch
    from api.utils.elasticsearch_telemetry_patch import (
        patch_elasticsearch_instrumentation,
    )

    patch_elasticsearch_instrumentation()

    instrumentor_map = {
        "elasticsearch": ElasticsearchInstrumentor,
        "requests": RequestsInstrumentor,
        "redis": RedisInstrumentor,
        "sqlalchemy": SQLAlchemyInstrumentor,
    }

    for package in getattr(settings, "OTEL_INSTRUMENTATION_PACKAGES", []):
        if package in instrumentor_map:
            instrumentor_map[package]().instrument()
