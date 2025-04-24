"""Custom middleware to handle CORS for OPTIONS requests."""

from typing import Any, Callable

from django.http import HttpRequest, HttpResponse


class OptionsCorsMiddleware:
    """Middleware that handles OPTIONS requests and adds CORS headers."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Handle OPTIONS requests directly
        if request.method == "OPTIONS":
            response = HttpResponse()
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE, PUT"
            response["Access-Control-Allow-Headers"] = (
                "DNT, User-Agent, X-Requested-With, If-Modified-Since, Cache-Control, "
                "Content-Type, Range, Authorization, x-keycloak-token, organization, "
                "dataspace, token"
            )
            response["Access-Control-Max-Age"] = "86400"
            return response

        # For non-OPTIONS requests, proceed normally
        response = self.get_response(request)

        # Ensure CORS headers are also added to regular responses
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE, PUT"

        return response
