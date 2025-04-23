"""Debug utilities for GraphQL resolvers."""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


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
