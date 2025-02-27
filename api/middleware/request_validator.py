import json
from django.http import JsonResponse
from typing import Any, Dict

class RequestValidationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.content_type == 'application/json' and request.body:
            try:
                json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse(
                    {'error': 'Invalid JSON in request body'},
                    status=400
                )

        # Add request ID for tracking
        request.id = self._generate_request_id()
        
        response = self.get_response(request)
        return response

    def _generate_request_id(self) -> str:
        import uuid
        return str(uuid.uuid4())
