from typing import Any, Dict, List, Optional

import structlog
from django.conf import settings
from django.db import transaction
from keycloak import KeycloakOpenID
from keycloak.exceptions import KeycloakError

from api.models import Organization
from authorization.models import OrganizationMembership, User

logger = structlog.getLogger(__name__)


class KeycloakManager:
    """
    Utility class to manage Keycloak integration with Django.
    Handles token validation, user synchronization, and role mapping.
    """

    def __init__(self) -> None:
        self.server_url = settings.KEYCLOAK_SERVER_URL
        self.realm = settings.KEYCLOAK_REALM
        self.client_id = settings.KEYCLOAK_CLIENT_ID
        self.client_secret = settings.KEYCLOAK_CLIENT_SECRET

        self.keycloak_openid = KeycloakOpenID(
            server_url=self.server_url,
            client_id=self.client_id,
            realm_name=self.realm,
            client_secret_key=self.client_secret,
        )

    def get_keycloak_client(self) -> KeycloakOpenID:
        """
        Get a Keycloak client instance.
        """
        return self.keycloak_openid

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
            token_info = self.keycloak_openid.introspect(token)
            if not token_info.get("active", False):
                logger.warning("Token is not active")
                return {}

            # Get user info from the token
            user_info = self.keycloak_openid.userinfo(token)
            return user_info
        except KeycloakError as e:
            logger.error(f"Error validating token: {e}")
            return {}

    def get_user_roles(self, token_info: dict) -> list[str]:
        """
        Extract roles from a Keycloak token.
        """
        roles: list[str] = []

        # Extract realm roles
        realm_access = token_info.get("realm_access", {})
        if realm_access and "roles" in realm_access:
            roles.extend(realm_access["roles"])  # type: ignore[no-any-return]

        # Extract client roles
        resource_access = token_info.get("resource_access", {})
        client_id = settings.KEYCLOAK_CLIENT_ID
        if resource_access and client_id in resource_access:
            client_roles = resource_access[client_id].get("roles", [])
            roles.extend(client_roles)

        return roles

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
        Creates or updates the User and UserOrganization records.

        Args:
            user_info: User information from Keycloak
            roles: User roles from Keycloak
            organizations: User organization memberships from Keycloak

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

            # Update user roles based on Keycloak roles
            if "admin" in roles:
                user.is_staff = True
                user.is_superuser = True
            else:
                user.is_staff = False
                user.is_superuser = False

            user.save()

            # Update organization memberships
            # First, get all existing organization memberships
            existing_memberships = OrganizationMembership.objects.filter(user=user)
            existing_org_ids = {
                membership.organization_id for membership in existing_memberships  # type: ignore[attr-defined]
            }

            # Process organizations from Keycloak
            for org_info in organizations:
                org_id = org_info.get("organization_id")
                role = org_info.get(
                    "role", "viewer"
                )  # Default to viewer if role not specified

                # Try to get the organization
                try:
                    organization = Organization.objects.get(id=org_id)  # type: ignore[misc]

                    # Create or update the membership
                    OrganizationMembership.objects.update_or_create(
                        user=user, organization=organization, defaults={"role": role}
                    )

                    # Remove from the set of existing memberships
                    if org_id in existing_org_ids:
                        existing_org_ids.remove(org_id)
                except Organization.DoesNotExist:
                    logger.warning(f"Organization with ID {org_id} does not exist")

            # Remove memberships that no longer exist in Keycloak
            if existing_org_ids:
                OrganizationMembership.objects.filter(
                    user=user, organization_id__in=existing_org_ids
                ).delete()

            return user
        except Exception as e:
            logger.error(f"Error synchronizing user from Keycloak: {e}")
            return None


# Create a singleton instance
keycloak_manager = KeycloakManager()
