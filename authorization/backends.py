from typing import Any, Dict, List, Optional, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

from api.utils.keycloak_utils import keycloak_manager
from authorization.models import User


class KeycloakAuthenticationBackend(ModelBackend):
    """
    Custom authentication backend for Django that authenticates users with Keycloak tokens.
    """

    def authenticate(  # type: ignore[override]
        self, request: Optional[HttpRequest] = None, token: Optional[str] = None, **kwargs: Any
    ) -> Optional[User]:
        """
        Authenticate a user based on a Keycloak token.

        Args:
            request: The request object
            token: The Keycloak token
            kwargs: Additional keyword arguments

        Returns:
            The authenticated user or None
        """
        if not token:
            return None

        # Validate the token and get user info
        user_info: Dict[str, Any] = keycloak_manager.validate_token(token)
        if not user_info:
            return None

        # Ensure we have a subject ID in the token
        if not user_info.get("sub"):
            return None

        # Get user roles and organizations from the token
        roles: List[str] = keycloak_manager.get_user_roles(token)
        organizations: List[Dict[str, Any]] = keycloak_manager.get_user_organizations(token)

        # Sync the user information with our database
        user: Optional[User] = keycloak_manager.sync_user_from_keycloak(
            user_info, roles, organizations
        )
        return user

    def get_user(self, user_id: int) -> Optional[User]:
        """
        Get a user by ID.

        Args:
            user_id: The user ID

        Returns:
            The user or None
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
