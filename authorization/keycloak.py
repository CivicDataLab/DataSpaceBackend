import logging
from typing import Any, Dict, List, Optional, Type, TypeVar, cast

from django.conf import settings
from django.db import transaction
from keycloak import KeycloakOpenID
from keycloak.exceptions import KeycloakError

from api.models import Organization
from authorization.models import OrganizationMembership, Role, User

logger = logging.getLogger(__name__)

# Type variables for model classes
T = TypeVar("T")


class KeycloakManager:
    """
    Utility class to manage Keycloak integration with Django.
    Handles token validation, user synchronization, and role mapping.
    """

    def __init__(self) -> None:
        self.server_url: str = settings.KEYCLOAK_SERVER_URL
        self.realm: str = settings.KEYCLOAK_REALM
        self.client_id: str = settings.KEYCLOAK_CLIENT_ID
        self.client_secret: str = settings.KEYCLOAK_CLIENT_SECRET

        self.keycloak_openid: KeycloakOpenID = KeycloakOpenID(
            server_url=self.server_url,
            client_id=self.client_id,
            realm_name=self.realm,
            client_secret_key=self.client_secret,
        )

    def get_token(self, username: str, password: str) -> Dict[str, Any]:
        """
        Get a Keycloak token for a user.

        Args:
            username: The username
            password: The password

        Returns:
            Dict containing the token information
        """
        try:
            return self.keycloak_openid.token(username, password)
        except KeycloakError as e:
            logger.error(f"Error getting token: {e}")
            raise

    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate a Keycloak token and return the user info.

        Args:
            token: The token to validate

        Returns:
            Dict containing the user information
        """
        try:
            # Verify the token is valid
            token_info: Dict[str, Any] = self.keycloak_openid.introspect(token)
            if not token_info.get("active", False):
                logger.warning("Token is not active")
                return {}

            # Get user info from the token
            user_info: Dict[str, Any] = self.keycloak_openid.userinfo(token)
            return user_info
        except KeycloakError as e:
            logger.error(f"Error validating token: {e}")
            return {}

    def get_user_roles(self, token: str) -> List[str]:
        """
        Get the roles for a user from their token.

        Args:
            token: The user's token

        Returns:
            List of role names
        """
        try:
            # Decode the token to get the roles
            token_info: Dict[str, Any] = self.keycloak_openid.decode_token(token)
            realm_access: Dict[str, Any] = token_info.get("realm_access", {})
            return cast(List[str], realm_access.get("roles", []))
        except KeycloakError as e:
            logger.error(f"Error getting user roles: {e}")
            return []

    def get_user_organizations(self, token: str) -> List[Dict[str, Any]]:
        """
        Get the organizations a user belongs to from their token.
        This assumes that organization information is stored in the token
        as client roles or in user attributes.

        Args:
            token: The user's token

        Returns:
            List of organization information
        """
        try:
            # Decode the token to get user info
            token_info = self.keycloak_openid.decode_token(token)

            # Get organization info from resource_access or attributes
            # This implementation depends on how organizations are represented in Keycloak
            # This is a simplified example - adjust based on your Keycloak configuration
            resource_access = token_info.get("resource_access", {})
            client_roles = resource_access.get(self.client_id, {}).get("roles", [])

            # Extract organization info from roles
            # Format could be 'org_<org_id>_<role>' or similar
            organizations = []
            for role in client_roles:
                if role.startswith("org_"):
                    parts = role.split("_")
                    if len(parts) >= 3:
                        org_id = parts[1]
                        role_name = parts[2]
                        organizations.append(
                            {"organization_id": org_id, "role": role_name}
                        )

            return organizations
        except KeycloakError as e:
            logger.error(f"Error getting user organizations: {e}")
            return []

    @transaction.atomic
    def sync_user_from_keycloak(
        self,
        user_info: Dict[str, Any],
        roles: List[str],
        organizations: List[Dict[str, Any]],
    ) -> Optional[User]:
        """
        Synchronize user information from Keycloak to Django.
        Creates or updates the User record and organization memberships.

        Args:
            user_info: User information from Keycloak
            roles: User roles from Keycloak (not used when maintaining roles in DB)
            organizations: User organizations from Keycloak

        Returns:
            The synchronized User object or None if failed
        """
        try:
            keycloak_id = user_info.get("sub")
            email = user_info.get("email")
            username = user_info.get("preferred_username") or email

            if not keycloak_id or not username:
                logger.error("Missing required user information from Keycloak")
                return None

            # Get or create the user
            user, created = User.objects.update_or_create(
                keycloak_id=keycloak_id,
                defaults={
                    "username": username,
                    "email": email,
                    "first_name": user_info.get("given_name", ""),
                    "last_name": user_info.get("family_name", ""),
                    "is_active": True,
                },
            )

            # We're not using Keycloak roles, so we don't update is_staff or is_superuser
            # If this is a new user, we'll keep default permissions
            if created:
                # You might want to assign default roles here
                pass

            user.save()

            # If this is a new user and we want to sync organization memberships
            # We'll only create new memberships for organizations found in Keycloak
            # but we won't update existing memberships or remove any
            if created and organizations:
                # Process organizations from Keycloak - only for new users
                for org_info in organizations:
                    org_id: Optional[str] = org_info.get("organization_id")
                    if not org_id:
                        continue

                    # Try to get the organization
                    try:
                        organization: Organization = Organization.objects.get(id=org_id)

                        # For new users, assign the default viewer role
                        # The actual role management will be done in the application
                        default_role: Role = Role.objects.get(name="viewer")

                        # Create the organization membership with default role
                        # Only if it doesn't already exist
                        OrganizationMembership.objects.get_or_create(
                            user=user,
                            organization=organization,
                            defaults={"role": default_role},
                        )
                    except Organization.DoesNotExist as e:
                        logger.error(
                            f"Error processing organization from Keycloak: {e}"
                        )
                    except Role.DoesNotExist as e:
                        logger.error(f"Default viewer role not found: {e}")

            # We don't remove organization memberships that are no longer in Keycloak
            # since we're maintaining roles in the database

            return user
        except Exception as e:
            logger.error(f"Error synchronizing user from Keycloak: {e}")
            return None


# Create a singleton instance
keycloak_manager = KeycloakManager()
