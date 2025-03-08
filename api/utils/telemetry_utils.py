"""Telemetry utilities for tracing and metrics."""

import functools
import time
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from opentelemetry import metrics, trace
from opentelemetry.metrics import Counter, Histogram, UpDownCounter
from opentelemetry.trace import Span, Status, StatusCode

# Type variable for generic function type
F = TypeVar("F", bound=Callable[..., Any])

# Get tracer and meter
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Define metrics
http_request_duration = meter.create_histogram(
    name="http_request_duration",
    description="Duration of HTTP requests",
    unit="ms",
)

api_requests_total = meter.create_counter(
    name="api_requests_total",
    description="Total number of API requests",
)

active_requests = meter.create_up_down_counter(
    name="active_requests",
    description="Number of currently active requests",
)


def trace_method(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, str]] = None,
    record_exceptions: bool = True,
) -> Callable[[F], F]:
    """Decorator to add OpenTelemetry tracing to a method.

    Args:
        name: Optional name for the span. If not provided, uses the function name.
        attributes: Optional attributes to add to the span.
        record_exceptions: Whether to record exceptions in the span.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get span name from parameter or function name
            span_name = name or func.__name__

            with tracer.start_as_current_span(span_name) as span:
                # Add attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Add function parameters as span attributes
                try:
                    # Skip 'self' parameter for instance methods
                    params = dict(zip(func.__code__.co_varnames[1:], args[1:]))
                    params.update(kwargs)
                    for key, value in params.items():
                        # Only add simple types as attributes
                        if isinstance(value, (str, int, float, bool)):
                            span.set_attribute(f"parameter.{key}", str(value))
                except Exception:
                    pass  # Skip parameter recording if it fails

                try:
                    # Record start time for metrics
                    start_time = time.time()

                    # Execute the function
                    result = func(*args, **kwargs)

                    # Record duration
                    duration_ms = (time.time() - start_time) * 1000
                    http_request_duration.record(duration_ms)

                    # Set span status
                    span.set_status(Status(StatusCode.OK))

                    return result

                except Exception as e:
                    if record_exceptions:
                        # Record exception in span
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        return cast(F, wrapper)

    return decorator


def track_metrics(
    name: Optional[str] = None,
    record_duration: bool = True,
) -> Callable[[F], F]:
    """Decorator to record metrics for a function.

    Args:
        name: Optional name prefix for metrics. If not provided, uses the function name.
        record_duration: Whether to record duration metrics.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            metric_name = name or func.__name__

            # Increment request counter
            api_requests_total.add(1, {"endpoint": metric_name})

            # Track active requests
            active_requests.add(1, {"endpoint": metric_name})

            try:
                start_time = time.time()
                result = func(*args, **kwargs)

                if record_duration:
                    duration_ms = (time.time() - start_time) * 1000
                    http_request_duration.record(duration_ms, {"endpoint": metric_name})

                return result

            finally:
                # Decrement active requests
                active_requests.add(-1, {"endpoint": metric_name})

        return cast(F, wrapper)

    return decorator
