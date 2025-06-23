# mypy: disable-error-code=valid-type
import threading
from typing import Any, Callable, Dict, Optional, TypedDict, TypeVar, cast

from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404

from api.models import DataSpace, Organization

User = get_user_model()

# Thread-local storage for the current user
_thread_locals = threading.local()


def get_current_user() -> Optional[User]:
    """
    Get the current user from thread-local storage.
    This is useful for tracking who performed an action when signals are triggered.
    """
    return getattr(_thread_locals, "user", None)


def set_current_user(user: Optional[User]) -> None:
    """
    Set the current user in thread-local storage.
    """
    _thread_locals.user = user


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
        # Set the current user in thread-local storage
        if hasattr(request, "user") and request.user.is_authenticated:
            set_current_user(request.user)
        else:
            set_current_user(None)

        # Get token from Authorization header (Bearer token) or x-keycloak-token header
        auth_header: Optional[str] = request.headers.get("authorization", None)
        keycloak_token: Optional[str] = request.headers.get("x-keycloak-token", None)

        # Extract token from Authorization header if present (remove 'Bearer ' prefix)
        auth_token: Optional[str] = None
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header[7:]
        elif keycloak_token:
            auth_token = keycloak_token

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

        # Clean up thread-local storage after request processing
        set_current_user(None)

        return response
