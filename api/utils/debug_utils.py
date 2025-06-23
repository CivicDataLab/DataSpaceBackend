"""Debug utilities for GraphQL resolvers and authentication."""

import json
import traceback
from typing import Any, Dict, Optional

import structlog
from django.http import HttpRequest

logger = structlog.getLogger(__name__)


def debug_context(info: Any, prefix: str = "Context") -> None:
    """
    Debug the GraphQL context object by logging its structure.
    This helps identify how to properly access user and request objects.
    """
    try:
        # Log the type of context
        logger.info(f"{prefix} type: {type(info.context)}")

        # If it's a dict, log its keys
        if isinstance(info.context, dict):
            logger.info(f"{prefix} keys: {list(info.context.keys())}")

            # Check if request is in the dict
            if "request" in info.context:
                request = info.context["request"]
                logger.info(f"{prefix} request type: {type(request)}")
                logger.info(f"{prefix} request attrs: {dir(request)[:20]}...")

                # Check if user is in the request
                if hasattr(request, "user"):
                    user = request.user
                    logger.info(f"{prefix} user type: {type(user)}")
                    logger.info(f"{prefix} user attrs: {dir(user)[:20]}...")

            # Check if user is directly in the dict
            if "user" in info.context:
                user = info.context["user"]
                logger.info(f"{prefix} direct user type: {type(user)}")

        # If it's an object, log its attributes
        else:
            logger.info(f"{prefix} attrs: {dir(info.context)[:20]}...")

            # Check if request is an attribute
            if hasattr(info.context, "request"):
                request = info.context
                logger.info(f"{prefix} request type: {type(request)}")
                logger.info(f"{prefix} request attrs: {dir(request)[:20]}...")

                # Check if user is in the request
                if hasattr(request, "user"):
                    user = request.user
                    logger.info(f"{prefix} user type: {type(user)}")

            # Check if user is directly an attribute
            if hasattr(info.context, "user"):
                user = info.context.user
                logger.info(f"{prefix} direct user type: {type(user)}")

    except Exception as e:
        logger.error(f"Error debugging context: {str(e)}")


def debug_auth_headers(request: Any, prefix: str = "Auth") -> None:
    """
    Debug authentication headers in the request.
    This helps identify if the token is being properly passed.
    """
    try:
        # Log all headers
        logger.info(f"{prefix} headers: {dict(request.headers.items())}")

        # Specifically log auth headers
        auth_header = request.headers.get("authorization", "")
        keycloak_token = request.headers.get("x-keycloak-token", "")

        (
            logger.info(f"{prefix} Authorization header: {auth_header[:20]}...")
            if auth_header
            else logger.info(f"{prefix} Authorization header: None")
        )
        (
            logger.info(f"{prefix} Keycloak token header: {keycloak_token[:20]}...")
            if keycloak_token
            else logger.info(f"{prefix} Keycloak token header: None")
        )

        # Log user info if available
        if hasattr(request, "user"):
            user = request.user
            logger.info(f"{prefix} User: {user}")
            logger.info(f"{prefix} User authenticated: {user.is_authenticated}")
            logger.info(
                f"{prefix} User ID: {user.id if hasattr(user, 'id') else 'No ID'}"
            )
    except Exception as e:
        logger.error(f"Error debugging auth headers: {str(e)}")
        logger.error(traceback.format_exc())


def debug_token_validation(
    token: str, user_info: Dict[str, Any], prefix: str = "Token"
) -> None:
    """
    Debug token validation results.
    This helps identify if the token is valid and what user info it contains.
    """
    try:
        logger.info(f"{prefix} Token present: {bool(token)}")
        logger.info(f"{prefix} Token length: {len(token) if token else 0}")
        logger.info(f"{prefix} User info present: {bool(user_info)}")

        if user_info:
            # Log key user info fields
            logger.info(f"{prefix} User sub: {user_info.get('sub', 'Not found')}")
            logger.info(f"{prefix} User email: {user_info.get('email', 'Not found')}")
            logger.info(
                f"{prefix} User preferred_username: {user_info.get('preferred_username', 'Not found')}"
            )
    except Exception as e:
        logger.error(f"Error debugging token validation: {str(e)}")
        logger.error(traceback.format_exc())
