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
        Validate a token (Django JWT or Keycloak) and return the user info.

        Args:
            token: The token to validate

        Returns:
            Dict containing the user information
        """
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        from rest_framework_simplejwt.tokens import AccessToken

        # First, try to validate as Django JWT token
        try:
            logger.debug("Attempting to validate as Django JWT token")
            access_token = AccessToken(token)  # type: ignore[arg-type]
            user_id = access_token.get("user_id")

            if user_id:
                logger.debug(f"Valid Django JWT token for user_id: {user_id}")
                try:
                    from authorization.models import User

                    user = User.objects.get(id=user_id)
                    # Return user info in Keycloak format
                    return {
                        "sub": (
                            str(user.keycloak_id)
                            if hasattr(user, "keycloak_id") and user.keycloak_id
                            else str(user.id)
                        ),
                        "preferred_username": user.username,
                        "email": user.email,
                        "given_name": user.first_name,
                        "family_name": user.last_name,
                    }
                except User.DoesNotExist:
                    logger.warning(f"User with id {user_id} not found in database")
        except (TokenError, InvalidToken) as e:
            logger.debug(f"Not a valid Django JWT token: {e}, trying Keycloak validation")
        except Exception as e:
            logger.debug(f"Error validating Django JWT: {e}, trying Keycloak validation")

        # If Django JWT validation failed, try Keycloak token validation
        try:
            # Verify the token is valid
            token_info = self.keycloak_openid.introspect(token)
            if not token_info.get("active", False):
                logger.warning("Token is not active")
                return {}

            # Try to get user info from the userinfo endpoint
            # If that fails (403), fall back to token introspection data
            try:
                user_info = self.keycloak_openid.userinfo(token)
                return user_info
            except KeycloakError as userinfo_error:
                # If userinfo fails (e.g., 403), extract user info from token introspection
                logger.warning(
                    f"Userinfo endpoint failed ({userinfo_error}), using token introspection data"
                )

                # Build user info from introspection response
                user_info = {
                    "sub": token_info.get("sub"),
                    "preferred_username": token_info.get("username")
                    or token_info.get("preferred_username"),
                    "email": token_info.get("email"),
                    "email_verified": token_info.get("email_verified", False),
                    "name": token_info.get("name"),
                    "given_name": token_info.get("given_name"),
                    "family_name": token_info.get("family_name"),
                }

                # Remove None values
                user_info = {k: v for k, v in user_info.items() if v is not None}
                return user_info

        except KeycloakError as e:
            logger.error(f"Error validating token: {e}")
            return {}

    def get_user_roles_from_token_info(self, token_info: dict) -> list[str]:
        """
        Extract roles from token introspection data.

        Args:
            token_info: Token introspection response

        Returns:
            List of role names
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

    def get_user_organizations_from_token_info(self, token_info: dict) -> List[Dict[str, Any]]:
        """
        Get organizations from token introspection data.

        Args:
            token_info: Token introspection response

        Returns:
            List of organization information
        """
        try:
            # Get organization info from resource_access or attributes
            resource_access = token_info.get("resource_access", {})
            client_roles = resource_access.get(self.client_id, {}).get("roles", [])

            # Extract organization info from roles
            organizations = []
            for role in client_roles:
                if role.startswith("org_"):
                    parts = role.split("_")
                    if len(parts) >= 3:
                        org_id = parts[1]
                        role_name = parts[2]
                        organizations.append({"organization_id": org_id, "role": role_name})

            return organizations
        except Exception as e:
            logger.error(f"Error getting user organizations: {e}")
            return []

    def get_user_roles(self, token: str) -> list[str]:
        """
        Extract roles from a Keycloak token.

        Args:
            token: The user's token

        Returns:
            List of role names
        """
        try:
            # Decode the token to get user info
            token_info = self.keycloak_openid.decode_token(token)

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
        except Exception as e:
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
                        organizations.append({"organization_id": org_id, "role": role_name})

            return organizations
        except KeycloakError as e:
            logger.error(f"Error getting user organizations: {e}")
            return []

    def update_user_in_keycloak(self, user: User) -> bool:
        """Update user details in Keycloak using admin credentials."""
        if not user.keycloak_id:
            logger.warning("Cannot update user in Keycloak: No keycloak_id", user_id=str(user.id))
            return False

        try:
            # Get admin credentials from settings
            admin_username = getattr(settings, "KEYCLOAK_ADMIN_USERNAME", "")
            admin_password = getattr(settings, "KEYCLOAK_ADMIN_PASSWORD", "")
            # Log credential presence (not the actual values)
            logger.info(
                "Admin credentials check",
                username_present=bool(admin_username),
                password_present=bool(admin_password),
            )

            if not admin_username or not admin_password:
                logger.error("Keycloak admin credentials not configured")
                return False

            from keycloak import KeycloakOpenID

            # First get an admin token directly
            keycloak_openid = KeycloakOpenID(
                server_url=self.server_url,
                client_id="admin-cli",  # Special client for admin operations
                realm_name="master",  # Admin users are in master realm
                verify=True,
            )

            # Get token
            try:
                token = keycloak_openid.token(
                    username=admin_username,
                    password=admin_password,
                    grant_type="password",
                )
                access_token = token.get("access_token")

                if not access_token:
                    logger.error("Failed to get admin access token")
                    return False

                # Now use the token to update the user
                import requests

                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                }

                user_data = {
                    "firstName": user.first_name,
                    "lastName": user.last_name,
                    "email": user.email,
                    "emailVerified": True,
                }

                # Direct API call to update user
                base_url = self.server_url.rstrip("/")  # Remove any trailing slash
                response = requests.put(
                    f"{base_url}/admin/realms/{self.realm}/users/{user.keycloak_id}",
                    headers=headers,
                    json=user_data,
                )

                if response.status_code == 204:  # Success for this endpoint
                    logger.info(
                        "Successfully updated user in Keycloak",
                        user_id=str(user.id),
                        keycloak_id=user.keycloak_id,
                    )
                    return True
                else:
                    logger.error(
                        f"Failed to update user in Keycloak: {response.status_code}: {response.text}",
                        user_id=str(user.id),
                    )
                    return False

            except Exception as token_error:
                logger.error(
                    f"Error getting admin token: {str(token_error)}",
                    user_id=str(user.id),
                )
                return False

        except Exception as e:
            logger.error(f"Error updating user in Keycloak: {str(e)}", user_id=str(user.id))
            return False

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
                role = org_info.get("role", "viewer")  # Default to viewer if role not specified

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
