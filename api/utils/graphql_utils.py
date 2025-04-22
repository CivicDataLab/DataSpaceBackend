"""Utility functions for GraphQL resolvers."""

from typing import Any, Optional, TypeVar, cast

from django.contrib.auth.models import AbstractUser, AnonymousUser
from django.http import HttpRequest
from strawberry.types import Info


def get_request_from_info(info: Info) -> Optional[HttpRequest]:
    """
    Extract the request object from the GraphQL info context.
    Handles both dictionary and object contexts.
    """
    if isinstance(info.context, dict):
        request = info.context.get("request")
        if request is None or isinstance(request, HttpRequest):
            return request
        return None  # Return None if request is not a HttpRequest
    elif hasattr(info.context, "request"):
        request = info.context.request
        if isinstance(request, HttpRequest):
            return request
        return None  # Return None if request is not a HttpRequest
    return None


def get_user_from_info(info: Info) -> Optional[AbstractUser]:
    """
    Extract the user object from the GraphQL info context.
    Handles both dictionary and object contexts.
    Returns None for anonymous users.
    """
    request = get_request_from_info(info)
    if not request:
        return None

    user = getattr(request, "user", None)
    if user and not isinstance(user, AnonymousUser):
        return cast(AbstractUser, user)
    return None


def is_authenticated(info: Info) -> bool:
    """
    Check if the user from the GraphQL info context is authenticated.
    """
    user = get_user_from_info(info)
    return user is not None and user.is_authenticated


def is_superuser(info: Info) -> bool:
    """
    Check if the user from the GraphQL info context is a superuser.
    """
    user = get_user_from_info(info)
    return user is not None and getattr(user, "is_superuser", False)
