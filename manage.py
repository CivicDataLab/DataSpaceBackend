#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from typing import List

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def main() -> None:
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DataSpace.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Set up OpenTelemetry
    resource = Resource.create({"service.name": "dataspace-backend"})
    provider: TracerProvider = TracerProvider(resource=resource)

    # Configure the exporter
    otlp_exporter = OTLPSpanExporter(
        endpoint=os.getenv("OTLP_ENDPOINT", "http://localhost:4317"), insecure=True
    )

    # Create and add span processor
    processor: BatchSpanProcessor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(processor)

    # Set the provider as the global tracer provider
    trace.set_tracer_provider(provider)

    # Initialize Django instrumentation
    DjangoInstrumentor().instrument()

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
