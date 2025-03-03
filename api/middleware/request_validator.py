import json
import uuid
from typing import Any, Callable, Dict

from django.http import HttpRequest, HttpResponse, JsonResponse


class RequestValidationMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.content_type == "application/json" and request.body:
            try:
                json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse(
                    {"error": "Invalid JSON in request body"}, status=400
                )

        # Add request ID for tracking
        setattr(request, "id", self._generate_request_id())

        response = self.get_response(request)
        return response

    def _generate_request_id(self) -> str:
        return str(uuid.uuid4())
