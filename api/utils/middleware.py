from typing import Any, Callable, Dict, Optional, TypedDict

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404

from api.models import DataSpace, Organization


class RequestContext(TypedDict):
    auth_token: Optional[str]
    organization: Optional[Organization]
    dataspace: Optional[DataSpace]


class CustomHttpRequest(HttpRequest):
    context: RequestContext


class ContextMiddleware:
    def __init__(
        self, get_response: Callable[[CustomHttpRequest], HttpResponse]
    ) -> None:
        self.get_response = get_response

    def __call__(self, request: CustomHttpRequest) -> HttpResponse:
        auth_token: Optional[str] = request.headers.get("authorization", None)
        organization_slug: Optional[str] = request.headers.get("organization", None)
        dataspace_slug: Optional[str] = request.headers.get("dataspace", None)

        # Validate and load the organization and dataspace objects
        try:
            if organization_slug is None:
                organization: Optional[Organization] = None
            else:
                organization = get_object_or_404(Organization, slug=organization_slug)
            if dataspace_slug is None:
                dataspace: Optional[DataSpace] = None
            else:
                dataspace = get_object_or_404(DataSpace, slug=dataspace_slug)
        except Organization.DoesNotExist:
            return JsonResponse({"error": "Invalid organization slug"}, status=400)
        except DataSpace.DoesNotExist:
            return JsonResponse({"error": "Invalid group slug"}, status=400)

        # TODO: resolve auth_token to user object before passing
        request.context = {
            "auth_token": auth_token,
            "organization": organization,
            "dataspace": dataspace,
        }

        response: HttpResponse = self.get_response(request)

        return response
