from typing import Any, Callable, Dict, List, Optional, cast

import structlog
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.utils.functional import SimpleLazyObject
from rest_framework.request import Request

from api.utils.debug_utils import debug_auth_headers, debug_token_validation
from authorization.keycloak import keycloak_manager
from authorization.models import User

logger = structlog.getLogger(__name__)


def get_user_from_keycloak_token(request: HttpRequest) -> User:
    """
    Get the user from the Keycloak token in the request.

    Args:
        request: The HTTP request

    Returns:
        The authenticated user or AnonymousUser
    """
    try:
        # Check if there's already a user in the request
        if hasattr(request, "_cached_user"):
            logger.debug("Using cached user from request")
            return request._cached_user  # type: ignore[attr-defined,no-any-return]

        # Get the token from the request
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        keycloak_token = request.META.get("HTTP_X_KEYCLOAK_TOKEN", "")

        # Also check headers directly (some frameworks use different capitalization)
        if not auth_header and hasattr(request, "headers"):
            auth_header = request.headers.get("authorization", "")
        if not keycloak_token and hasattr(request, "headers"):
            keycloak_token = request.headers.get("x-keycloak-token", "")

        # Log headers for debugging
        logger.debug(
            f"Auth header: {auth_header[:10]}... Keycloak token: {keycloak_token[:10]}..."
        )

        # Try to get token from Authorization header first
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove 'Bearer ' prefix
            logger.debug("Found token in Authorization header")
        # If not found, try the x-keycloak-token header
        elif keycloak_token:
            token = keycloak_token
            logger.debug("Found token in x-keycloak-token header")

        # If no token found, return anonymous user
        if not token:
            logger.debug("No token found, returning anonymous user")
            return cast(User, AnonymousUser())

        # Validate the token and get user info
        user_info: Dict[str, Any] = keycloak_manager.validate_token(token)

        # Debug token validation
        debug_token_validation(token, user_info)

        if not user_info:
            logger.warning("Token validation failed, returning anonymous user")
            return cast(User, AnonymousUser())

        # Get user roles and organizations from the token
        roles = keycloak_manager.get_user_roles(token)
        organizations = keycloak_manager.get_user_organizations(token)

        logger.debug(f"User roles from token: {roles}")
        logger.debug(f"User organizations from token: {organizations}")

        # Sync the user information with our database
        user = keycloak_manager.sync_user_from_keycloak(user_info, roles, organizations)
        if not user:
            logger.warning("User synchronization failed, returning anonymous user")
            return cast(User, AnonymousUser())

        logger.debug(
            f"Successfully authenticated user: {user.username} (ID: {user.id})"
        )

        # Cache the user for future requests
        lazy_user = SimpleLazyObject(lambda: user)
        request._cached_user = lazy_user  # type: ignore[attr-defined,assignment]
        return user
    except Exception as e:
        logger.error(f"Error in get_user_from_keycloak_token: {str(e)}")
        return cast(User, AnonymousUser())


class KeycloakAuthenticationMiddleware:
    """
    Middleware to authenticate users with Keycloak tokens.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        logger.info("KeycloakAuthenticationMiddleware initialized")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Skip authentication for OPTIONS requests
        if request.method == "OPTIONS":
            logger.debug("Skipping authentication for OPTIONS request")
            return self.get_response(request)

        # Debug request headers
        debug_auth_headers(request)

        # Process the request before the view is called
        if not hasattr(request, "user") or request.user.is_anonymous:
            logger.debug("Setting user from Keycloak token")
            # Set user directly instead of using SimpleLazyObject to avoid potential issues
            try:
                request.user = get_user_from_keycloak_token(request)
                logger.debug(
                    f"User set: {request.user}, authenticated: {request.user.is_authenticated}"
                )
            except Exception as e:
                logger.error(f"Error setting user: {str(e)}")
                request.user = AnonymousUser()
        else:
            logger.debug(
                f"User already set: {request.user}, authenticated: {request.user.is_authenticated}"
            )

        # Call the next middleware or view
        response = self.get_response(request)

        return response
