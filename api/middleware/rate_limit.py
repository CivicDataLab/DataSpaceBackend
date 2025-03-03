from typing import Callable, cast

from django.http import HttpRequest, HttpResponse
from django_ratelimit.decorators import ratelimit  # type: ignore[import]
from django_ratelimit.exceptions import Ratelimited  # type: ignore[import]


class HttpResponseTooManyRequests(HttpResponse):
    status_code = 429


def rate_limit_middleware(
    get_response: Callable[[HttpRequest], HttpResponse]
) -> Callable[[HttpRequest], HttpResponse]:
    def middleware(request: HttpRequest) -> HttpResponse:
        # Apply rate limiting based on IP
        @ratelimit(key="ip", rate="100/h", method=["GET", "POST", "PUT", "DELETE"])
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
        except Exception:
            # Log unexpected errors but still return 429 to avoid leaking error info
            return cast(HttpResponse, HttpResponseTooManyRequests())

    return middleware
