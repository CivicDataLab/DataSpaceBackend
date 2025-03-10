"""GraphQL telemetry extension for Strawberry."""

import asyncio
import functools
import time
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    Optional,
    TypeVar,
    Union,
    cast,
)

import strawberry
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from strawberry.extensions import SchemaExtension
from strawberry.types import Info

from api.utils.telemetry_utils import meter

# Type variable for generic function type
F = TypeVar("F", bound=Callable[..., Any])

# Create metrics
graphql_request_duration = meter.create_histogram(
    name="graphql_request_duration",
    description="Duration of GraphQL operations",
    unit="ms",
)

graphql_requests_total = meter.create_counter(
    name="graphql_requests_total",
    description="Total number of GraphQL requests",
)

graphql_errors_total = meter.create_counter(
    name="graphql_errors_total",
    description="Total number of GraphQL errors",
)


def trace_resolver(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, str]] = None,
) -> Callable[[F], F]:
    """Decorator to add OpenTelemetry tracing to a GraphQL resolver.

    Args:
        name: Optional name for the span. If not provided, uses the function name.
        attributes: Optional attributes to add to the span.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get the resolver name
            span_name = name or func.__name__

            # Get GraphQL info from args
            info = next((arg for arg in args if isinstance(arg, Info)), None)

            # Get parent span from context if available
            parent_span = (
                info.context.get("telemetry_span") if info and info.context else None
            )

            with trace.get_tracer(__name__).start_span(
                f"resolver.{span_name}",
                context=parent_span.get_span_context() if parent_span else None,
            ) as span:
                # Add base attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Add GraphQL context if available
                if info:
                    span.set_attribute("graphql.field", info.field_name)
                    span.set_attribute("graphql.operation", str(info.operation))
                    if info.variable_values:
                        span.set_attribute(
                            "graphql.variables", str(info.variable_values)
                        )

                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    # Record metrics
                    graphql_request_duration.record(
                        duration_ms,
                        {
                            "operation": "query" if info else "unknown",
                            "field": info.field_name if info else "unknown",
                        },
                    )
                    graphql_requests_total.add(
                        1,
                        {
                            "operation": "query" if info else "unknown",
                            "field": info.field_name if info else "unknown",
                        },
                    )
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(e)
                    graphql_errors_total.add(
                        1,
                        {
                            "operation": "query" if info else "unknown",
                            "field": info.field_name if info else "unknown",
                            "error": e.__class__.__name__,
                        },
                    )
                    raise

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get the resolver name
            span_name = name or func.__name__

            # Get GraphQL info from args
            info = next((arg for arg in args if isinstance(arg, Info)), None)

            # Get parent span from context if available
            parent_span = (
                info.context.get("telemetry_span") if info and info.context else None
            )

            with trace.get_tracer(__name__).start_span(
                f"resolver.{span_name}",
                context=parent_span.get_span_context() if parent_span else None,
            ) as span:
                # Add base attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Add GraphQL context if available
                if info:
                    span.set_attribute("graphql.field", info.field_name)
                    span.set_attribute("graphql.operation", str(info.operation))
                    if info.variable_values:
                        span.set_attribute(
                            "graphql.variables", str(info.variable_values)
                        )

                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000

                    # Record metrics
                    graphql_request_duration.record(
                        duration_ms,
                        {
                            "operation": "query" if info else "unknown",
                            "field": info.field_name if info else "unknown",
                        },
                    )
                    graphql_requests_total.add(
                        1,
                        {
                            "operation": "query" if info else "unknown",
                            "field": info.field_name if info else "unknown",
                        },
                    )
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR))
                    span.record_exception(e)
                    graphql_errors_total.add(
                        1,
                        {
                            "operation": "query" if info else "unknown",
                            "field": info.field_name if info else "unknown",
                            "error": e.__class__.__name__,
                        },
                    )
                    raise

        if asyncio.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    return decorator


class TelemetryExtension(SchemaExtension):
    """Strawberry extension to add OpenTelemetry tracing to all operations."""

    def on_operation(self) -> Iterator[None]:
        """Handle operation start."""
        try:
            if not self.execution_context.operation_type:
                yield
                return
        except RuntimeError:
            # Skip telemetry for introspection queries
            yield
            return

        start_time = time.time()

        # Start span for the operation
        span = trace.get_tracer(__name__).start_span(
            f"graphql.{self.execution_context.operation_type}",
            attributes={
                "graphql.operation_name": self.execution_context.operation_name
                or "anonymous",
                "graphql.operation_type": str(self.execution_context.operation_type),
                "graphql.query": str(self.execution_context.query),
            },
        )

        # Store span in context for later use
        self.execution_context.context["telemetry_span"] = span

        try:
            yield
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR))
            span.record_exception(e)
            graphql_errors_total.add(
                1,
                {
                    "operation": str(self.execution_context.operation_type),
                    "error": e.__class__.__name__,
                },
            )
            raise
        finally:
            duration = (time.time() - start_time) * 1000  # Convert to milliseconds
            graphql_request_duration.record(
                duration,
                {
                    "operation": str(self.execution_context.operation_type),
                    "name": self.execution_context.operation_name or "anonymous",
                },
            )
            graphql_requests_total.add(
                1,
                {
                    "operation": str(self.execution_context.operation_type),
                    "name": self.execution_context.operation_name or "anonymous",
                },
            )
            span.end()

    def on_validation_error(self, errors: Any) -> None:
        """Handle validation errors."""
        graphql_errors_total.add(
            1,
            {
                "operation": "validation",
                "error": "ValidationError",
            },
        )

    def on_error(self, error: Exception) -> None:
        """Handle operation errors."""
        graphql_errors_total.add(
            1,
            {
                "operation": "execution",
                "error": error.__class__.__name__,
            },
        )
