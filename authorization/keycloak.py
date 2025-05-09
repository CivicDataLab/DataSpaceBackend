from typing import Any, Dict, List, Optional, Type, TypeVar, cast

import structlog
from django.conf import settings
from django.db import transaction
from keycloak import KeycloakAdmin, KeycloakOpenID
from keycloak.exceptions import KeycloakError

from api.models import Organization
from authorization.models import OrganizationMembership, Role, User

logger = structlog.getLogger(__name__)

# Type variables for model classes
T = TypeVar("T")


class KeycloakManager:
    """
    Utility class to manage Keycloak integration with Django.
    Handles token validation, user synchronization, and role mapping.
    """

    def __init__(self) -> None:
        import structlog

        logger = structlog.getLogger(__name__)

        self.server_url: str = settings.KEYCLOAK_SERVER_URL
        self.realm: str = settings.KEYCLOAK_REALM
        self.client_id: str = settings.KEYCLOAK_CLIENT_ID
        self.client_secret: str = settings.KEYCLOAK_CLIENT_SECRET

        # Log Keycloak connection details (without secrets)
        logger.debug(
            f"Initializing Keycloak connection to {self.server_url} "
            f"for realm {self.realm} and client {self.client_id}"
        )

        try:
            self.keycloak_openid: KeycloakOpenID = KeycloakOpenID(
                server_url=self.server_url,
                client_id=self.client_id,
                realm_name=self.realm,
                client_secret_key=self.client_secret,
            )

            logger.debug("Keycloak client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Keycloak client: {e}")
            # Use cast to satisfy the type checker
            self.keycloak_openid = cast(KeycloakOpenID, object())

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
        Only validates by contacting Keycloak directly - no local validation.

        Args:
            token: The token to validate

        Returns:
            Dict containing the user information or empty dict if validation fails
        """
        import structlog

        logger = structlog.getLogger(__name__)

        # Log token for debugging
        logger.debug(f"Validating token of length: {len(token)}")

        # Only try to contact Keycloak directly - don't create users from local token decoding
        try:
            logger.debug("Attempting to get user info from Keycloak")
            user_info = self.keycloak_openid.userinfo(token)
            if user_info and isinstance(user_info, dict):
                logger.debug("Successfully retrieved user info from Keycloak")
                logger.debug(f"User info: {user_info}")
                return user_info
            else:
                logger.warning("Keycloak returned empty or invalid user info")
                return {}
        except Exception as e:
            logger.warning(f"Failed to get user info from Keycloak: {e}")
            return {}

    def get_user_roles(self, token: str) -> List[str]:
        """
        Get the roles for a user from their token.

        Args:
            token: The user's token

        Returns:
            List of role names
        """
        import structlog
        from django.conf import settings

        logger = structlog.getLogger(__name__)

        # Get roles directly from token
        logger.debug("Extracting roles from token")

        logger.debug(f"Getting roles from token of length: {len(token)}")

        try:
            # Decode the token to get the roles
            try:
                token_info: Dict[str, Any] = self.keycloak_openid.decode_token(token)
                logger.debug("Successfully decoded token for roles")
            except Exception as decode_error:
                logger.warning(f"Failed to decode token for roles: {decode_error}")
                # If we can't decode the token, try to get roles from introspection
                try:
                    token_info = self.keycloak_openid.introspect(token)
                    logger.debug("Using introspection result for roles")
                except Exception as introspect_error:
                    logger.error(
                        f"Failed to introspect token for roles: {introspect_error}"
                    )
                    return []

            # Extract roles from token info
            realm_access: Dict[str, Any] = token_info.get("realm_access", {})
            roles = cast(List[str], realm_access.get("roles", []))

            # Also check resource_access for client roles
            resource_access = token_info.get("resource_access", {})
            client_roles = resource_access.get(self.client_id, {}).get("roles", [])

            # Combine realm and client roles
            all_roles = list(set(roles + client_roles))
            logger.debug(f"Found roles: {all_roles}")

            return all_roles
        except KeycloakError as e:
            logger.error(f"Error getting user roles: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting user roles: {e}")
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
        import structlog
        from django.conf import settings

        logger = structlog.getLogger(__name__)

        logger.debug(f"Getting organizations from token of length: {len(token)}")

        try:
            # Decode the token to get user info
            token_info = {}
            try:
                token_info = self.keycloak_openid.decode_token(token)
                logger.debug("Successfully decoded token for organizations")
            except Exception as decode_error:
                logger.warning(
                    f"Failed to decode token for organizations: {decode_error}"
                )
                # If we can't decode the token, try to get info from introspection
                try:
                    token_info = self.keycloak_openid.introspect(token)
                    logger.debug("Using introspection result for organizations")
                except Exception as introspect_error:
                    logger.error(
                        f"Failed to introspect token for organizations: {introspect_error}"
                    )
                    return []

            # Get organization info from resource_access or attributes
            # This implementation depends on how organizations are represented in Keycloak
            resource_access = token_info.get("resource_access", {})
            client_roles = resource_access.get(self.client_id, {}).get("roles", [])

            logger.debug(f"Found client roles: {client_roles}")

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

            # If no organizations found through roles, check user attributes
            if not organizations and token_info.get("attributes"):
                attrs = token_info.get("attributes", {})
                org_attrs = attrs.get("organizations", [])

                if isinstance(org_attrs, str):
                    org_attrs = [org_attrs]  # Convert single string to list

                for org_attr in org_attrs:
                    try:
                        # Format could be 'org_id:role'
                        org_id, role = org_attr.split(":")
                        organizations.append({"organization_id": org_id, "role": role})
                    except ValueError:
                        # If no role specified, use default
                        organizations.append(
                            {"organization_id": org_attr, "role": "viewer"}
                        )

            logger.debug(f"Found organizations: {organizations}")
            return organizations
        except KeycloakError as e:
            logger.error(f"Error getting user organizations: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting user organizations: {e}")
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
        import structlog

        logger = structlog.getLogger(__name__)

        # Log the user info we're trying to sync
        logger.debug(f"Attempting to sync user with info: {user_info}")

        try:
            # Extract key user information
            keycloak_id = user_info.get("sub")
            email = user_info.get("email")
            username = user_info.get("preferred_username") or email

            # Validate required fields
            if not keycloak_id or not username:
                logger.error("Missing required user information from Keycloak")
                return None

            # Initialize variables
            user = None
            created = False

            # Try to find user by keycloak_id first
            try:
                user = User.objects.get(keycloak_id=keycloak_id)
                logger.debug(f"Found existing user by keycloak_id: {user.username}")

                # Update user details
                user.username = str(username) if username else ""  # type: ignore[assignment]
                user.email = str(email) if email else ""  # type: ignore[assignment]
                user.first_name = (
                    str(user_info.get("given_name", ""))
                    if user_info.get("given_name")
                    else ""
                )
                user.last_name = (
                    str(user_info.get("family_name", ""))
                    if user_info.get("family_name")
                    else ""
                )
                user.is_active = True
                user.save()
            except User.DoesNotExist:
                # Try to find user by email
                if email:
                    try:
                        user = User.objects.get(email=email)
                        logger.debug(f"Found existing user by email: {user.username}")

                        # Update keycloak_id and other details
                        user.keycloak_id = str(keycloak_id) if keycloak_id else ""  # type: ignore[assignment]
                        user.username = str(username) if username else ""  # type: ignore[assignment]
                        user.first_name = (
                            str(user_info.get("given_name", ""))
                            if user_info.get("given_name")
                            else ""
                        )
                        user.last_name = (
                            str(user_info.get("family_name", ""))
                            if user_info.get("family_name")
                            else ""
                        )
                        user.is_active = True
                        user.save()
                    except User.DoesNotExist:
                        # Try to find user by username
                        try:
                            user = User.objects.get(username=username)
                            logger.debug(
                                f"Found existing user by username: {user.username}"
                            )

                            # Update keycloak_id and other details
                            user.keycloak_id = str(keycloak_id) if keycloak_id else ""  # type: ignore[assignment]
                            user.email = str(email) if email else ""  # type: ignore[assignment]
                            user.first_name = (
                                str(user_info.get("given_name", ""))
                                if user_info.get("given_name")
                                else ""
                            )
                            user.last_name = (
                                str(user_info.get("family_name", ""))
                                if user_info.get("family_name")
                                else ""
                            )
                            user.is_active = True
                            user.save()
                        except User.DoesNotExist:
                            # Create new user
                            logger.debug(
                                f"Creating new user with keycloak_id: {keycloak_id}"
                            )
                            user = User.objects.create(
                                keycloak_id=str(keycloak_id) if keycloak_id else "",  # type: ignore[arg-type]
                                username=str(username) if username else "",  # type: ignore[arg-type]
                                email=str(email) if email else "",  # type: ignore[arg-type]
                                first_name=(
                                    str(user_info.get("given_name", ""))
                                    if user_info.get("given_name")
                                    else ""
                                ),
                                last_name=(
                                    str(user_info.get("family_name", ""))
                                    if user_info.get("family_name")
                                    else ""
                                ),
                                is_active=True,
                            )
                            created = True

            # If this is a new user, we'll keep default permissions
            if created:
                pass

            if user is not None:  # Check that user is not None before saving
                user.save()

            # If this is a new user and we want to sync organization memberships
            # We'll only create new memberships for organizations found in Keycloak
            # but we won't update existing memberships or remove any
            if user is not None and created and organizations:
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

    def update_user_in_keycloak(self, user: User) -> bool:
        """Update user details in Keycloak using admin credentials."""
        if not user.keycloak_id:
            logger.warning(
                "Cannot update user in Keycloak: No keycloak_id", user_id=str(user.id)
            )
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
            logger.error(
                f"Error updating user in Keycloak: {str(e)}", user_id=str(user.id)
            )
            return False


# Create a singleton instance
keycloak_manager = KeycloakManager()
