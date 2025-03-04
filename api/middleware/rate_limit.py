import logging
from typing import Any, Callable, TypeVar, cast

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django_ratelimit.decorators import ratelimit  # type: ignore[import]
from django_ratelimit.exceptions import Ratelimited  # type: ignore[import]
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Type variables for view functions
ViewFunc = TypeVar("ViewFunc", bound=Callable[..., HttpResponse])


class HttpResponseTooManyRequests(HttpResponse):
    status_code = 429


def safe_ratelimit(
    key: str, rate: str, method: list[str]
) -> Callable[[ViewFunc], ViewFunc]:
    """Custom rate limiter that falls back to allowing requests if Redis fails."""

    def decorator(view_func: ViewFunc) -> ViewFunc:
        def wrapped_view(
            request: HttpRequest, *args: Any, **kwargs: Any
        ) -> HttpResponse:
            try:
                # Try to use the regular rate limiter
                @ratelimit(key=key, rate=rate, method=method)
                def rate_limited_view(request: HttpRequest) -> HttpResponse:
                    return view_func(request, *args, **kwargs)

                return cast(HttpResponse, rate_limited_view(request))
            except RedisError as e:
                # Log the Redis error but allow the request
                logger.error(f"Rate limit cache error: {str(e)}")
                return cast(HttpResponse, view_func(request, *args, **kwargs))

        return cast(ViewFunc, wrapped_view)

    return decorator


def rate_limit_middleware(
    get_response: Callable[[HttpRequest], HttpResponse]
) -> Callable[[HttpRequest], HttpResponse]:
    def middleware(request: HttpRequest) -> HttpResponse:
        # Apply rate limiting based on IP with fallback
        @safe_ratelimit(key="ip", rate="1000/h", method=["POST", "PUT", "DELETE"])
        @safe_ratelimit(key="ip", rate="5000/h", method=["GET"])
        def check_rate_limit(request: HttpRequest) -> HttpResponse:
            return get_response(request)

        try:
            response = cast(HttpResponse, check_rate_limit(request))
            return (
                response
                if response
                else cast(HttpResponse, HttpResponseTooManyRequests())
            )
        except Ratelimited:
            return cast(HttpResponse, HttpResponseTooManyRequests())
        except RedisError as e:
            # Log Redis errors but allow the request
            logger.error(f"Rate limit middleware Redis error: {str(e)}")
            return get_response(request)
        except Exception as e:
            # Log unexpected errors but still return 429 to avoid leaking error info
            logger.error(f"Rate limit middleware unexpected error: {str(e)}")
            return cast(HttpResponse, HttpResponseTooManyRequests())

    return middleware
