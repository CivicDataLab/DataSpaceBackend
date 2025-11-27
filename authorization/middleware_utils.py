from typing import Any, Callable, Dict, List, Optional, cast

import structlog
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils.functional import SimpleLazyObject
from rest_framework.request import Request
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from api.utils.debug_utils import debug_auth_headers, debug_token_validation
from api.utils.keycloak_utils import keycloak_manager
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
        # Always validate the token on each request to ensure user is synchronized
        logger.debug("Validating token for request")

        # Extract token from Authorization header with improved robustness
        token = None
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        # If no Authorization header in META, try the headers attribute
        if not auth_header and hasattr(request, "headers"):
            auth_header = request.headers.get("authorization", "")

        # Clean up auth_header if it exists
        if auth_header:
            auth_header = auth_header.strip()
            logger.debug(f"Auth header found: {auth_header[:30]}...")

            # Check if it's a Bearer token (case insensitive)
            if auth_header.lower().startswith("bearer "):
                token = auth_header[7:].strip()  # Remove 'Bearer ' prefix
                logger.debug(f"Extracted Bearer token, length: {len(token)}")
            else:
                # Use the raw header value, but check if it might be a raw token
                # (no 'Bearer ' prefix but still a valid JWT format)
                token = auth_header
                logger.debug(f"Using raw Authorization header as token, length: {len(token)}")

        # If no token found, return anonymous user
        if not token:
            logger.debug("No token found, returning anonymous user")
            return cast(User, AnonymousUser())

        # Log token details for debugging
        logger.debug(f"Processing token of length: {len(token)}")
        logger.debug(f"Token type: {type(token)}")
        logger.debug(f"Token value: {token}")

        # Simple direct approach - validate the token and get user info
        logger.debug(f"Validating token directly: {token[:30]}...")

        # For debugging, print the raw token
        logger.debug(f"Raw token: {token}")

        # First, try to validate as Django JWT token
        try:
            logger.debug("Attempting to validate as Django JWT token")
            access_token = AccessToken(token)
            user_id = access_token.get("user_id")

            if user_id:
                logger.debug(f"Valid Django JWT token for user_id: {user_id}")
                try:
                    user = User.objects.get(id=user_id)
                    logger.debug(f"Successfully authenticated user via Django JWT: {user.username}")
                    return user
                except User.DoesNotExist:
                    logger.warning(f"User with id {user_id} not found in database")
        except (TokenError, InvalidToken) as e:
            logger.debug(f"Not a valid Django JWT token: {e}, trying Keycloak validation")
        except Exception as e:
            logger.debug(f"Error validating Django JWT: {e}, trying Keycloak validation")

        # If Django JWT validation failed, try Keycloak token validation
        try:
            logger.debug("Attempting to validate as Keycloak token")
            # Try direct validation without any complex logic
            user_info = keycloak_manager.validate_token(token)

            if not user_info:
                logger.error("Token validation failed, returning anonymous user")
                return cast(User, AnonymousUser())

            # Check if we have a valid subject ID from Keycloak
            if not user_info.get("sub"):
                logger.error(
                    "Token validation succeeded but missing subject ID, returning anonymous user"
                )
                return cast(User, AnonymousUser())

            logger.debug(f"Token validation successful, user info: {user_info}")
        except Exception as e:
            logger.error(f"Exception during token validation: {e}")
            return cast(User, AnonymousUser())

        # Log the user info for debugging
        logger.debug(f"User info from token: {user_info.keys() if user_info else 'None'}")
        logger.debug(f"User sub: {user_info.get('sub', 'None')}")
        logger.debug(f"User email: {user_info.get('email', 'None')}")
        logger.debug(f"User preferred_username: {user_info.get('preferred_username', 'None')}")

        # Get user roles and organizations from the token
        roles = keycloak_manager.get_user_roles(token)
        organizations = keycloak_manager.get_user_organizations(token)

        logger.debug(f"User roles from token: {roles}")
        logger.debug(f"User organizations from token: {organizations}")

        # Sync the user information with our database
        synced_user = keycloak_manager.sync_user_from_keycloak(user_info, roles, organizations)
        if not synced_user:
            logger.warning("User synchronization failed, returning anonymous user")
            return cast(User, AnonymousUser())

        logger.debug(
            f"Successfully authenticated user: {synced_user.username} (ID: {synced_user.id})"
        )

        # Return the authenticated user
        logger.debug(f"Returning authenticated user: {synced_user.username}")
        return synced_user
    except Exception as e:
        logger.error(f"Error in get_user_from_keycloak_token: {str(e)}")
        return cast(User, AnonymousUser())
