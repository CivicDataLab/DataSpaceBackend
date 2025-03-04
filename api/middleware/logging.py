import structlog
import time
from typing import Any, Dict

logger = structlog.get_logger()

class StructuredLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()

        # Pre-processing log
        logger.info(
            "request_started",
            path=request.path,
            method=request.method,
            request_id=getattr(request, 'id', None)
        )

        response = self.get_response(request)

        # Post-processing log
        duration = time.time() - start_time
        logger.info(
            "request_finished",
            path=request.path,
            method=request.method,
            status=response.status_code,
            duration=duration,
            request_id=getattr(request, 'id', None)
        )

        return response

    def process_exception(self, request, exception):
        logger.error(
            "request_failed",
            path=request.path,
            method=request.method,
            error=str(exception),
            request_id=getattr(request, 'id', None)
        )
        return None
