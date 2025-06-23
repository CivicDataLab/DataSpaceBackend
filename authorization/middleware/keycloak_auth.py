from typing import Any, Callable, cast

import structlog
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse

from authorization.middleware_utils import (  # Import from middleware.py
    get_user_from_keycloak_token,
)
from authorization.models import User

logger = structlog.getLogger(__name__)


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
