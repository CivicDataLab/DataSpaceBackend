from typing import Any, Callable, Dict, List, Optional, cast

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.utils.functional import SimpleLazyObject
from rest_framework.request import Request

from authorization.keycloak import keycloak_manager
from authorization.models import User


def get_user_from_keycloak_token(request: HttpRequest) -> User:
    """
    Get the user from the Keycloak token in the request.

    Args:
        request: The HTTP request

    Returns:
        The authenticated user or AnonymousUser
    """
    # Check if there's already a user in the request
    if hasattr(request, "_cached_user"):
        return request._cached_user  # type: ignore[attr-defined,no-any-return]

    # Get the token from the request
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    keycloak_token = request.META.get("HTTP_X_KEYCLOAK_TOKEN", "")

    # Try to get token from Authorization header first
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove 'Bearer ' prefix
    # If not found, try the x-keycloak-token header
    elif keycloak_token:
        token = keycloak_token

    # If no token found, return anonymous user
    if not token:
        return cast(User, AnonymousUser())

    # Validate the token and get user info
    user_info: Dict[str, Any] = keycloak_manager.validate_token(token)
    if not user_info:
        return cast(User, AnonymousUser())

    # Get user roles and organizations from the token
    roles = keycloak_manager.get_user_roles(token)
    organizations = keycloak_manager.get_user_organizations(token)

    # Sync the user information with our database
    user = keycloak_manager.sync_user_from_keycloak(user_info, roles, organizations)
    if not user:
        return cast(User, AnonymousUser())

    # Cache the user for future requests
    lazy_user = SimpleLazyObject(lambda: user)
    request._cached_user = lazy_user  # type: ignore[attr-defined,assignment]
    return user


class KeycloakAuthenticationMiddleware:
    """
    Middleware to authenticate users with Keycloak tokens.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Skip authentication for OPTIONS requests
        if request.method == "OPTIONS":
            return self.get_response(request)

        # Process the request before the view is called
        if not hasattr(request, "user") or request.user.is_anonymous:
            request.user = SimpleLazyObject(  # type: ignore[assignment]
                lambda: get_user_from_keycloak_token(request)
            )

        # Call the next middleware or view
        response = self.get_response(request)

        return response
