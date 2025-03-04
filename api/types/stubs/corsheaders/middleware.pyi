"""Type stubs for django-cors-headers.middleware"""

from typing import Any, Callable, List, Optional, Set, Union

from django.http import HttpRequest, HttpResponse

class CorsMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None: ...
    def __call__(self, request: HttpRequest) -> HttpResponse: ...
    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse: ...
