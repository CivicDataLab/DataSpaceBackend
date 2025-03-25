import time
from typing import Any, Callable, Optional

import structlog
from django.http import HttpRequest, HttpResponse

logger = structlog.get_logger()


class StructuredLoggingMiddleware:
    """Middleware for structured logging of requests and responses."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Initialize the middleware with a get_response callable."""
        self.get_response = get_response
        # Paths to exclude from logging
        self.exclude_paths = ["/health/"]

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Process the request and log timing information."""
        start_time = time.time()

        # Skip logging for excluded paths (like health checks)
        should_log = request.path not in self.exclude_paths

        # Pre-processing log (only if not excluded)
        if should_log:
            logger.info(
                "request_started",
                path=request.path,
                method=request.method,
                request_id=getattr(request, "id", None),
            )

        response = self.get_response(request)

        # Post-processing log (only if not excluded)
        if should_log:
            duration = time.time() - start_time
            logger.info(
                "request_finished",
                path=request.path,
                method=request.method,
                status=response.status_code,
                duration=duration,
                request_id=getattr(request, "id", None),
            )

        return response

    def process_exception(
        self, request: HttpRequest, exception: Exception
    ) -> Optional[HttpResponse]:
        """Handle and log any exceptions that occur during request processing."""
        # Skip logging for excluded paths (like health checks)
        if request.path not in self.exclude_paths:
            logger.error(
                "request_failed",
                path=request.path,
                method=request.method,
                error=str(exception),
                request_id=getattr(request, "id", None),
            )
        return None
