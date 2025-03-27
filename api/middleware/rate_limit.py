import logging
import time
from typing import Any, Callable, Optional, cast

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class HttpResponseTooManyRequests(HttpResponse):
    status_code = 429


def rate_limit_middleware(
    get_response: Callable[[HttpRequest], HttpResponse]
) -> Callable[[HttpRequest], HttpResponse]:
    """Rate limiting middleware that uses a simple cache-based counter."""

    def get_client_ip(request: HttpRequest) -> str:
        """Get the client IP from the request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = cast(str, x_forwarded_for.split(",")[0].strip())
            return ip
        ip = cast(str, request.META.get("REMOTE_ADDR", ""))
        return ip

    def check_rate_limit(request: HttpRequest) -> bool:
        """Check if the request should be rate limited."""

        try:
            client_ip = get_client_ip(request)
            method = request.method

            # Different limits for different methods
            if method == "GET":
                limit = 5000
                window = 3600  # 1 hour in seconds
            else:
                limit = 1000
                window = 3600

            # Create cache keys
            count_key = f"ratelimit:{client_ip}:{method}:count"
            reset_key = f"ratelimit:{client_ip}:{method}:reset"

            # Try to get current count and reset time
            count = cast(int, cache.get(count_key, 0))
            reset_time = cast(Optional[int], cache.get(reset_key))

            current_time = int(time.time())

            # If reset time is in the past or doesn't exist, reset the counter
            if not reset_time or current_time > reset_time:
                count = 0
                reset_time = current_time + window
                cache.set(reset_key, reset_time, window)

            # Increment counter
            count += 1
            cache.set(count_key, count, window)

            logger.info(
                f"Rate limit check - Method: {method}, Path: {request.path}, "
                f"IP: {client_ip}, Count: {count}/{limit}, "
                f"Reset in: {reset_time - current_time}s"
            )

            return cast(bool, count <= limit)

        except RedisError as e:
            logger.error(f"Redis error in rate limiter: {str(e)}")
            return True  # Allow request on Redis error
        except Exception as e:
            logger.error(f"Unexpected error in rate limiter: {str(e)}")
            return True  # Allow request on unexpected error

    def middleware(request: HttpRequest) -> HttpResponse:
        if not check_rate_limit(request):
            logger.warning(
                f"Rate limited - Method: {request.method}, "
                f"Path: {request.path}, IP: {get_client_ip(request)}"
            )
            return HttpResponseTooManyRequests()

        return get_response(request)

    return middleware
