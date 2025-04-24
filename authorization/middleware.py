from typing import Any, Callable, Dict, List, Optional, cast

import structlog
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
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
        # DEVELOPMENT MODE: Check for a special header that indicates we should use a superuser
        # This is for development/debugging only and should be removed in production
        dev_mode = getattr(settings, "KEYCLOAK_DEV_MODE", False)
        if dev_mode:
            logger.warning(
                "KEYCLOAK_DEV_MODE is enabled - using development authentication"
            )
            # Try to get the first superuser
            try:
                superuser = User.objects.filter(is_superuser=True).first()
                if superuser:
                    logger.info(f"Using superuser {superuser.username} for development")
                    # Cache the user for future requests
                    lazy_user = SimpleLazyObject(lambda: superuser)
                    request._cached_user = lazy_user  # type: ignore[attr-defined,assignment]
                    return superuser
                else:
                    # No superuser exists, log this as an error
                    logger.error(
                        "No superuser found in the database. Please create one using 'python manage.py promote_to_superuser'"
                    )
            except Exception as e:
                logger.error(f"Error setting up development user: {e}")

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

        # Check for session-based authentication
        session_token = None
        if hasattr(request, "session") and "access_token" in request.session:
            session_token = request.session.get("access_token")
            logger.debug("Found access_token in session")

        # Check for token in request body (for GraphQL operations)
        body_token = None
        if hasattr(request, "body") and request.body:
            try:
                import json

                body_data = json.loads(request.body)
                if isinstance(body_data, dict) and "token" in body_data:
                    body_token = body_data.get("token")
                    logger.debug("Found token in request body")
            except Exception as e:
                logger.debug(f"Failed to parse request body: {e}")

        # Log headers for debugging
        if auth_header:
            logger.debug(f"Auth header present, length: {len(auth_header)}")
            if len(auth_header) > 20:
                logger.debug(f"Auth header starts with: {auth_header[:20]}...")
                logger.debug(f"Auth header ends with: ...{auth_header[-20:]}")

                # Check if it looks like a JWT
                import re

                jwt_pattern = re.compile(
                    r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
                )
                if jwt_pattern.search(auth_header):
                    logger.debug(
                        "Auth header contains what appears to be a JWT pattern"
                    )

                # Check if it's a very long token (possibly raw from session)
                if len(auth_header) > 1000:
                    logger.debug(
                        "Auth header contains a very long token, possibly raw from session"
                    )

        if keycloak_token:
            logger.debug(f"Keycloak token present, length: {len(keycloak_token)}")

        if session_token:
            logger.debug(f"Session token present, length: {len(session_token)}")

        # Try to get token from various sources, in order of preference
        token = None

        # 1. Try session token first (most reliable)
        if session_token:
            token = session_token
            logger.debug(f"Using access_token from session, length: {len(token)}")
            if len(token) > 20:
                logger.debug(
                    f"Session token starts with: {token[:10]}..., ends with: ...{token[-10:]}"
                )

        # 2. Try Authorization header
        elif auth_header:
            # Check if it has Bearer prefix
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]  # Remove 'Bearer ' prefix
                logger.debug("Found Bearer token in Authorization header")
            else:
                # Use the raw Authorization header value as the token
                token = auth_header
                logger.debug(
                    f"Found raw token in Authorization header, length: {len(token)}"
                )
                # Log first and last few characters for debugging
                if len(token) > 20:
                    logger.debug(
                        f"Token starts with: {token[:10]}..., ends with: ...{token[-10:]}"
                    )

                # If token is very long (>1000 chars), it might be a raw token from a frontend
                # that hasn't been properly formatted. Let's log this for debugging.
                if len(token) > 1000:
                    logger.warning(
                        f"Token is unusually long ({len(token)} chars). This might be a raw token."
                    )

        # 3. Try the x-keycloak-token header
        elif keycloak_token:
            token = keycloak_token
            logger.debug("Found token in x-keycloak-token header")

        # 4. Try token from request body
        elif body_token:
            token = body_token
            logger.debug("Found token in request body")

        # If no token found, return anonymous user
        if not token:
            logger.debug("No token found, returning anonymous user")
            return cast(User, AnonymousUser())

        # Validate the token and get user info
        logger.debug(f"Attempting to validate token of length {len(token)}")
        user_info: Dict[str, Any] = keycloak_manager.validate_token(token)

        # Debug token validation
        debug_token_validation(token, user_info)

        if not user_info:
            logger.warning("Token validation failed, returning anonymous user")
            # Try one more time with a different approach for very long tokens
            if len(token) > 1000:
                logger.debug("Trying alternative token extraction for long token")
                # Try to extract a JWT pattern from the long token
                import re

                jwt_pattern = re.compile(
                    r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
                )
                jwt_match = jwt_pattern.search(token)
                if jwt_match:
                    extracted_jwt = jwt_match.group(0)
                    logger.debug(
                        f"Found potential JWT within token: {extracted_jwt[:10]}...{extracted_jwt[-10:]}"
                    )
                    # Try validating the extracted JWT
                    user_info = keycloak_manager.validate_token(extracted_jwt)
                    if user_info:
                        logger.info("Successfully validated extracted JWT")
                        token = extracted_jwt  # Use the extracted JWT for subsequent operations
                    else:
                        logger.warning("Failed to validate extracted JWT")

            if not user_info:
                return cast(User, AnonymousUser())

        # Log the user info for debugging
        logger.debug(
            f"User info from token: {user_info.keys() if user_info else 'None'}"
        )
        logger.debug(f"User sub: {user_info.get('sub', 'None')}")
        logger.debug(f"User email: {user_info.get('email', 'None')}")
        logger.debug(
            f"User preferred_username: {user_info.get('preferred_username', 'None')}"
        )

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
