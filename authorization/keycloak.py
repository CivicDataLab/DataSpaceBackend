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
        import structlog

        logger = structlog.getLogger(__name__)

        self.server_url: str = settings.KEYCLOAK_SERVER_URL
        self.realm: str = settings.KEYCLOAK_REALM
        self.client_id: str = settings.KEYCLOAK_CLIENT_ID
        self.client_secret: str = settings.KEYCLOAK_CLIENT_SECRET

        # Log Keycloak connection details (without secrets)
        logger.info(
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
            logger.info("Keycloak client initialized successfully")
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

        Args:
            token: The token to validate

        Returns:
            Dict containing the user information
        """
        import json

        import structlog
        from django.conf import settings

        logger = structlog.getLogger(__name__)

        # Check if we're in development mode
        dev_mode = getattr(settings, "KEYCLOAK_DEV_MODE", False)
        if dev_mode:
            logger.warning("KEYCLOAK_DEV_MODE is enabled - using mock token validation")
            # Return a mock user_info for development
            return {
                "sub": "dev-user-id",
                "email": "admin@example.com",
                "preferred_username": "admin",
                "given_name": "Admin",
                "family_name": "User",
                "roles": ["admin"],
            }

        # Log token length for debugging
        logger.debug(f"Validating token of length: {len(token)}")

        # For very long tokens (>1000 chars), try to extract a JWT first
        if len(token) > 1000:
            logger.debug("Token is very long, attempting to extract JWT pattern")
            import re

            jwt_pattern = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
            jwt_match = jwt_pattern.search(token)
            if jwt_match:
                extracted_jwt = jwt_match.group(0)
                logger.debug(
                    f"Found potential JWT within long token: {extracted_jwt[:10]}...{extracted_jwt[-10:]}"
                )
                # Try with the extracted JWT
                try:
                    result = self.validate_token(extracted_jwt)
                    if result:
                        logger.info("Successfully validated extracted JWT")
                        return result
                except Exception as e:
                    logger.warning(f"Failed to validate extracted JWT: {e}")

        # If this is a raw token from a frontend session, it might be the access_token directly
        # Let's try to decode it directly before attempting introspection
        try:
            logger.debug("Attempting direct token decode before introspection")
            decoded_token = self.keycloak_openid.decode_token(token)
            if decoded_token and isinstance(decoded_token, dict):
                logger.info("Successfully decoded token directly")
                # Extract user info from the decoded token
                extracted_user_info = {
                    "sub": decoded_token.get("sub"),
                    "email": decoded_token.get("email"),
                    "preferred_username": decoded_token.get("preferred_username")
                    or decoded_token.get("username"),
                    "given_name": decoded_token.get("given_name")
                    or decoded_token.get("firstName"),
                    "family_name": decoded_token.get("family_name")
                    or decoded_token.get("lastName"),
                    "roles": decoded_token.get("realm_access", {}).get("roles", [])
                    or decoded_token.get("roles", []),
                }

                # Log the extracted user info for debugging
                logger.debug(
                    f"Extracted user info from direct decode: {extracted_user_info.keys() if extracted_user_info else 'None'}"
                )
                if extracted_user_info.get("sub"):
                    return extracted_user_info
        except Exception as e:
            logger.debug(
                f"Direct token decode failed: {e}, continuing with standard validation"
            )

        try:
            # Verify the token is valid
            logger.debug("Attempting to introspect token")
            token_info: Dict[str, Any] = {}

            try:
                # Log token format for debugging
                logger.debug(
                    f"Token format check: alphanumeric only: {token.isalnum()}"
                )

                # Try standard introspection first
                try:
                    token_info = self.keycloak_openid.introspect(token)
                    logger.debug(
                        f"Token introspection result: active={token_info.get('active', False)}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Standard introspection failed: {e}, trying alternative methods"
                    )
            except Exception as introspect_error:
                logger.warning(f"Token introspection failed: {introspect_error}")
                # If introspection fails, try to decode the token directly
                try:
                    logger.debug("Attempting to decode token directly")

                    # First, try to extract a JWT if this is a non-standard format
                    # Look for JWT pattern: base64url.base64url.base64url
                    import re

                    jwt_pattern = re.compile(
                        r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
                    )
                    jwt_match = jwt_pattern.search(token)

                    if jwt_match:
                        extracted_jwt = jwt_match.group(0)
                        logger.debug(
                            f"Found potential JWT within token: {extracted_jwt[:10]}...{extracted_jwt[-10:]}"
                        )
                        try:
                            # Try to decode the extracted JWT
                            decoded_token = self.keycloak_openid.decode_token(
                                extracted_jwt
                            )
                            if decoded_token and isinstance(decoded_token, dict):
                                token_info = {"active": True}
                                logger.debug("Successfully decoded extracted JWT")
                                # Use the extracted JWT for subsequent operations
                                token = extracted_jwt
                                return self.validate_token(
                                    token
                                )  # Restart validation with extracted token
                        except Exception as jwt_error:
                            logger.warning(
                                f"Failed to decode extracted JWT: {jwt_error}"
                            )

                    # If no JWT found or JWT decode failed, try the original token
                    decoded_token = self.keycloak_openid.decode_token(token)
                    # If we can decode it, consider it valid for now
                    if decoded_token and isinstance(decoded_token, dict):
                        token_info = {"active": True}
                        logger.debug("Successfully decoded token")
                except Exception as decode_error:
                    logger.error(f"Token decode failed: {decode_error}")
                    return {}

            if not token_info.get("active", False):
                logger.warning("Token is not active")
                return {}

            # Get user info from the token
            logger.debug("Attempting to get user info from token")
            user_info: Dict[str, Any] = {}

            try:
                user_info = self.keycloak_openid.userinfo(token)
                logger.debug(
                    f"Successfully retrieved user info: {user_info.keys() if user_info else 'None'}"
                )
            except Exception as userinfo_error:
                logger.warning(f"Failed to get user info: {userinfo_error}")
                # Try to extract user info from the decoded token
                try:
                    decoded_token = self.keycloak_openid.decode_token(token)
                    # Extract basic user info from token claims
                    extracted_user_info = {
                        "sub": decoded_token.get("sub"),
                        "email": decoded_token.get("email"),
                        "preferred_username": decoded_token.get("preferred_username")
                        or decoded_token.get("username"),
                        "given_name": decoded_token.get("given_name")
                        or decoded_token.get("firstName"),
                        "family_name": decoded_token.get("family_name")
                        or decoded_token.get("lastName"),
                        "roles": decoded_token.get("realm_access", {}).get("roles", [])
                        or decoded_token.get("roles", []),
                    }

                    # Log the extracted user info for debugging
                    logger.debug(
                        f"Extracted user info from token: {extracted_user_info.keys() if extracted_user_info else 'None'}"
                    )
                    if "sub" in extracted_user_info:
                        logger.debug(f"User sub: {extracted_user_info['sub']}")
                    if "email" in extracted_user_info:
                        logger.debug(f"User email: {extracted_user_info['email']}")
                    if "preferred_username" in extracted_user_info:
                        logger.debug(
                            f"User preferred_username: {extracted_user_info['preferred_username']}"
                        )
                except Exception as extract_error:
                    logger.error(
                        f"Failed to extract user info from token: {extract_error}"
                    )
                    return {}

            return user_info
        except KeycloakError as e:
            logger.error(f"Error validating token: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error validating token: {e}")
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

        # Check if we're in development mode
        dev_mode = getattr(settings, "KEYCLOAK_DEV_MODE", False)
        if dev_mode:
            logger.warning("KEYCLOAK_DEV_MODE is enabled - using mock roles")
            # Return mock roles for development
            return ["admin", "manager", "viewer"]

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

        # Check if we're in development mode
        dev_mode = getattr(settings, "KEYCLOAK_DEV_MODE", False)
        if dev_mode:
            logger.warning("KEYCLOAK_DEV_MODE is enabled - using mock organizations")
            # Return mock organizations for development
            # Try to get real organizations from the database
            try:
                from api.models import Organization

                # Get up to 5 organizations
                orgs = Organization.objects.all()[:5]
                if orgs.exists():
                    # Use a more generic approach that doesn't depend on specific attribute names
                    return [
                        {"organization_id": str(getattr(org, "id", getattr(org, "pk", "mock-org-id"))), "role": "admin"}  # type: ignore[attr-defined]
                        for org in orgs
                    ]
            except Exception as e:
                logger.error(f"Failed to get organizations from database: {e}")

            # Fallback to a mock organization
            return [{"organization_id": "mock-org-id", "role": "admin"}]

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
        from django.conf import settings

        logger = structlog.getLogger(__name__)

        # Check if we're in development mode
        dev_mode = getattr(settings, "KEYCLOAK_DEV_MODE", False)
        if dev_mode:
            logger.warning(
                "KEYCLOAK_DEV_MODE is enabled - using superuser for development"
            )
            # Try to get a superuser
            try:
                superuser = User.objects.filter(is_superuser=True).first()
                if superuser:
                    logger.info(f"Using superuser {superuser.username} for development")
                    return superuser

                # If no superuser exists, create one
                logger.info("No superuser found, creating one for development")
                admin_user = User.objects.create(
                    username="admin",
                    email="admin@example.com",
                    first_name="Admin",
                    last_name="User",
                    is_staff=True,
                    is_superuser=True,
                    is_active=True,
                    keycloak_id="dev-user-id",
                )
                admin_user.set_password("admin")  # Set a default password
                admin_user.save()
                return admin_user
            except Exception as e:
                logger.error(f"Error setting up development user: {e}")

        try:
            keycloak_id = user_info.get("sub")
            email = user_info.get("email")
            username = user_info.get("preferred_username") or email

            if not keycloak_id or not username:
                logger.error("Missing required user information from Keycloak")
                return None

            # Try to find user by keycloak_id first
            user = None
            created = False

            try:
                user = User.objects.get(keycloak_id=keycloak_id)
                logger.info(f"Found existing user by keycloak_id: {user.username}")
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
                try:
                    if email:
                        user = User.objects.get(email=email)
                        logger.info(f"Found existing user by email: {user.username}")
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
                        logger.info(f"Found existing user by username: {user.username}")
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
                        logger.info(
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


# Create a singleton instance
keycloak_manager = KeycloakManager()
