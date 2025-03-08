"""Initialize OpenTelemetry instrumentation."""

import os
from typing import Optional

from django.conf import settings
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.elasticsearch import ElasticsearchInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
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

    # Create TracerProvider with resource
    tracer_provider = TracerProvider(resource=resource)

    # Set up exporters
    otlp_exporter = OTLPSpanExporter(
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        insecure=True,  # TODO: Configure with proper TLS in production
    )

    # Add span processors
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Add console exporter in development for debugging
    if settings.DEBUG:
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Initialize instrumentors if enabled in settings
    if getattr(settings, "OTEL_PYTHON_DJANGO_INSTRUMENT", True):
        DjangoInstrumentor().instrument(
            request_hook=lambda span, request: (
                span.set_attribute(
                    "http.request.headers",
                    str(dict(request.headers)),
                )
                if hasattr(request, "headers")
                else None
            ),
            response_hook=lambda span, response: (
                span.set_attribute(
                    "http.response.headers",
                    str(dict(response.headers)),
                )
                if hasattr(response, "headers")
                else None
            ),
        )

    for package in getattr(settings, "OTEL_INSTRUMENTATION_PACKAGES", []):
        if package == "elasticsearch":
            ElasticsearchInstrumentor().instrument()
        elif package == "requests":
            RequestsInstrumentor().instrument()
        elif package == "redis":
            RedisInstrumentor().instrument()
        elif package == "sqlalchemy":
            SQLAlchemyInstrumentor().instrument()

    # Create and return tracer for manual instrumentation
    return trace.get_tracer(__name__)
