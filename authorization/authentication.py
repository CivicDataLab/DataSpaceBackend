from typing import Any, Dict, Optional, Tuple, cast

from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from authorization.keycloak import keycloak_manager
from authorization.models import User


class KeycloakAuthentication(BaseAuthentication):
    """
    Custom authentication class for Django REST Framework that authenticates users with Keycloak tokens.
    """

    def authenticate(self, request: Request) -> Optional[Tuple[User, str]]:
        """
        Authenticate the request and return a two-tuple of (user, token).

        Args:
            request: The request to authenticate

        Returns:
            A tuple of (user, token) if authentication succeeds, None otherwise

        Raises:
            AuthenticationFailed: If the token is invalid or user sync fails
        """
        # Get the token from the request
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Validate the token and get user info
        user_info: Dict[str, Any] = keycloak_manager.validate_token(token)
        if not user_info:
            raise AuthenticationFailed("Invalid or expired token")

        # Ensure we have a subject ID in the token
        if not user_info.get("sub"):
            raise AuthenticationFailed(
                "Token validation succeeded but missing subject ID"
            )

        # Get user roles and organizations from the token
        roles = keycloak_manager.get_user_roles(token)
        organizations = keycloak_manager.get_user_organizations(token)

        # Sync the user information with our database
        user = keycloak_manager.sync_user_from_keycloak(user_info, roles, organizations)
        if not user:
            raise AuthenticationFailed("Failed to synchronize user information")

        return (user, token)

    def authenticate_header(self, request: Request) -> str:
        """
        Return a string to be used as the value of the `WWW-Authenticate`
        header in a `401 Unauthenticated` response, or `None` if the
        authentication scheme should return `403 Permission Denied` responses.

        Args:
            request: The request to authenticate

        Returns:
            Authentication header string
        """
        return 'Bearer realm="dataexchange"'
