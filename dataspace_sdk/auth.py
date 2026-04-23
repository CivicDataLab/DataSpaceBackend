"""Authentication module for DataSpace SDK."""

import time
from typing import Any, Dict, Optional

import requests

from dataspace_sdk.exceptions import DataSpaceAuthError


class AuthClient:
    """Handles authentication with DataSpace API."""

    def __init__(
        self,
        base_url: str,
        keycloak_url: Optional[str] = None,
        keycloak_realm: Optional[str] = None,
        keycloak_client_id: Optional[str] = None,
        keycloak_client_secret: Optional[str] = None,
    ):
        """
        Initialize the authentication client.

        Args:
            base_url: Base URL of the DataSpace API
            keycloak_url: Keycloak server URL (e.g., "https://opub-kc.civicdatalab.in")
            keycloak_realm: Keycloak realm name (e.g., "DataSpace")
            keycloak_client_id: Keycloak client ID (e.g., "dataspace")
            keycloak_client_secret: Optional client secret for confidential clients
        """
        self.base_url = base_url.rstrip("/")
        self.keycloak_url = keycloak_url.rstrip("/") if keycloak_url else None
        self.keycloak_realm = keycloak_realm
        self.keycloak_client_id = keycloak_client_id
        self.keycloak_client_secret = keycloak_client_secret

        # Session state
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.keycloak_access_token: Optional[str] = None
        self.keycloak_refresh_token: Optional[str] = None
        self.token_expires_at: Optional[float] = None
        self.user_info: Optional[Dict] = None

        # Stored credentials for auto-relogin
        self._username: Optional[str] = None
        self._password: Optional[str] = None

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        Login using username and password via Keycloak.

        Args:
            username: User's username or email
            password: User's password

        Returns:
            Dictionary containing user info and tokens

        Raises:
            DataSpaceAuthError: If authentication fails
        """
        if not all([self.keycloak_url, self.keycloak_realm, self.keycloak_client_id]):
            raise DataSpaceAuthError(
                "Keycloak configuration missing. Please provide keycloak_url, "
                "keycloak_realm, and keycloak_client_id when initializing the client."
            )

        # Store credentials for auto-relogin
        self._username = username
        self._password = password

        # Get Keycloak token
        keycloak_token = self._get_keycloak_token(username, password)

        # Login to DataSpace backend
        return self._login_with_keycloak_token(keycloak_token)

    def login_as_service_account(self) -> Dict[str, Any]:
        """
        Login using client credentials (service account).

        This method authenticates the client itself (not a user) using
        the client_id and client_secret. Requires the Keycloak client
        to have "Service Accounts Enabled".

        Returns:
            Dictionary containing user info and tokens

        Raises:
            DataSpaceAuthError: If authentication fails
        """
        if not all(
            [
                self.keycloak_url,
                self.keycloak_realm,
                self.keycloak_client_id,
                self.keycloak_client_secret,
            ]
        ):
            raise DataSpaceAuthError(
                "Service account authentication requires keycloak_url, "
                "keycloak_realm, keycloak_client_id, and keycloak_client_secret."
            )

        # Get Keycloak token using client credentials
        keycloak_token = self._get_service_account_token()

        # Login to DataSpace backend
        return self._login_with_keycloak_token(keycloak_token)

    def _get_keycloak_token(self, username: str, password: str) -> str:
        """
        Get Keycloak access token using username and password.

        Args:
            username: User's username or email
            password: User's password

        Returns:
            Keycloak access token

        Raises:
            DataSpaceAuthError: If authentication fails
        """
        token_url = (
            f"{self.keycloak_url}/auth/realms/{self.keycloak_realm}/"
            f"protocol/openid-connect/token"
        )

        data = {
            "grant_type": "password",
            "client_id": self.keycloak_client_id,
            "username": username,
            "password": password,
        }

        if self.keycloak_client_secret:
            data["client_secret"] = self.keycloak_client_secret

        try:
            response = requests.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 200:
                token_data = response.json()
                self.keycloak_access_token = token_data.get("access_token")
                self.keycloak_refresh_token = token_data.get("refresh_token")

                # Calculate token expiration time
                expires_in = token_data.get("expires_in", 300)
                self.token_expires_at = time.time() + expires_in

                if not self.keycloak_access_token:
                    raise DataSpaceAuthError("No access token in Keycloak response")

                return self.keycloak_access_token
            else:
                error_data = response.json()
                error_msg = error_data.get(
                    "error_description",
                    error_data.get("error", "Keycloak authentication failed"),
                )
                raise DataSpaceAuthError(
                    f"Keycloak login failed: {error_msg}",
                    status_code=response.status_code,
                    response=error_data,
                )
        except requests.RequestException as e:
            raise DataSpaceAuthError(f"Network error during Keycloak authentication: {str(e)}")

    def _get_service_account_token(self) -> str:
        """
        Get Keycloak access token using client credentials (service account).

        Returns:
            Keycloak access token

        Raises:
            DataSpaceAuthError: If authentication fails
        """
        token_url = (
            f"{self.keycloak_url}/auth/realms/{self.keycloak_realm}/"
            f"protocol/openid-connect/token"
        )

        data = {
            "grant_type": "client_credentials",
            "client_id": self.keycloak_client_id,
            "client_secret": self.keycloak_client_secret,
        }

        try:
            response = requests.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 200:
                token_data = response.json()
                self.keycloak_access_token = token_data.get("access_token")
                self.keycloak_refresh_token = token_data.get("refresh_token")

                # Calculate token expiration time
                expires_in = token_data.get("expires_in", 300)
                self.token_expires_at = time.time() + expires_in

                if not self.keycloak_access_token:
                    raise DataSpaceAuthError("No access token in Keycloak response")

                return self.keycloak_access_token
            else:
                error_data = response.json()
                error_msg = error_data.get(
                    "error_description",
                    error_data.get("error", "Service account authentication failed"),
                )
                raise DataSpaceAuthError(
                    f"Service account login failed: {error_msg}. "
                    f"Ensure 'Service Accounts Enabled' is ON in Keycloak client settings.",
                    status_code=response.status_code,
                    response=error_data,
                )
        except requests.RequestException as e:
            raise DataSpaceAuthError(
                f"Network error during service account authentication: {str(e)}"
            )

    def _refresh_keycloak_token(self) -> str:
        """
        Refresh Keycloak access token using refresh token.

        Returns:
            New Keycloak access token

        Raises:
            DataSpaceAuthError: If token refresh fails
        """
        if not self.keycloak_refresh_token:
            # If no refresh token, try to relogin with stored credentials
            if self._username and self._password:
                return self._get_keycloak_token(self._username, self._password)
            raise DataSpaceAuthError("No refresh token or credentials available")

        token_url = (
            f"{self.keycloak_url}/auth/realms/{self.keycloak_realm}/"
            f"protocol/openid-connect/token"
        )

        data = {
            "grant_type": "refresh_token",
            "client_id": self.keycloak_client_id,
            "refresh_token": self.keycloak_refresh_token,
        }

        if self.keycloak_client_secret:
            data["client_secret"] = self.keycloak_client_secret

        try:
            response = requests.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 200:
                token_data = response.json()
                self.keycloak_access_token = token_data.get("access_token")
                self.keycloak_refresh_token = token_data.get("refresh_token")

                expires_in = token_data.get("expires_in", 300)
                self.token_expires_at = time.time() + expires_in

                if not self.keycloak_access_token:
                    raise DataSpaceAuthError("No access token in refresh response")

                return self.keycloak_access_token
            else:
                # Refresh failed, try to relogin with stored credentials
                if self._username and self._password:
                    return self._get_keycloak_token(self._username, self._password)
                raise DataSpaceAuthError("Keycloak token refresh failed")
        except requests.RequestException as e:
            # Network error, try to relogin with stored credentials
            if self._username and self._password:
                return self._get_keycloak_token(self._username, self._password)
            raise DataSpaceAuthError(f"Network error during token refresh: {str(e)}")

    def _ensure_valid_keycloak_token(self) -> str:
        """
        Ensure we have a valid Keycloak token, refreshing if necessary.

        Returns:
            Valid Keycloak access token

        Raises:
            DataSpaceAuthError: If unable to get valid token
        """
        # Check if token is expired or about to expire (within 30 seconds)
        if (
            not self.keycloak_access_token
            or not self.token_expires_at
            or time.time() >= (self.token_expires_at - 30)
        ):
            # Token expired or about to expire, refresh it
            if self.keycloak_refresh_token or (self._username and self._password):
                return self._refresh_keycloak_token()
            raise DataSpaceAuthError("No valid token or credentials available")

        return self.keycloak_access_token

    def _login_with_keycloak_token(self, keycloak_token: str) -> Dict[str, Any]:
        """
        Login using a Keycloak token.

        Args:
            keycloak_token: Valid Keycloak access token

        Returns:
            Dictionary containing user info and tokens

        Raises:
            DataSpaceAuthError: If authentication fails
        """
        url = f"{self.base_url}/api/auth/keycloak/login/"

        try:
            response = requests.post(
                url,
                json={"token": keycloak_token},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                data: Dict[str, Any] = response.json()
                self.access_token = data.get("access")
                self.refresh_token = data.get("refresh")
                self.user_info = data.get("user")
                return data
            else:
                error_msg = response.json().get("error", "Authentication failed")
                raise DataSpaceAuthError(
                    error_msg,
                    status_code=response.status_code,
                    response=response.json(),
                )
        except requests.RequestException as e:
            raise DataSpaceAuthError(f"Network error during authentication: {str(e)}")

    def refresh_access_token(self) -> str:
        """
        Refresh the access token using the refresh token.

        Returns:
            New access token

        Raises:
            DataSpaceAuthError: If token refresh fails
        """
        if not self.refresh_token:
            raise DataSpaceAuthError("No refresh token available")

        url = f"{self.base_url}/api/auth/token/refresh/"

        try:
            response = requests.post(
                url,
                json={"refresh": self.refresh_token},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access")
                if self.access_token is None:
                    raise DataSpaceAuthError("Token refresh returned no access token")
                return self.access_token
            else:
                raise DataSpaceAuthError(
                    "Token refresh failed",
                    status_code=response.status_code,
                    response=response.json(),
                )
        except requests.RequestException as e:
            raise DataSpaceAuthError(f"Network error during token refresh: {str(e)}")

    def get_user_info(self) -> Dict[str, Any]:
        """
        Get current user information.

        Returns:
            Dictionary containing user information

        Raises:
            DataSpaceAuthError: If request fails
        """
        if not self.access_token:
            raise DataSpaceAuthError("Not authenticated. Please login first.")

        url = f"{self.base_url}/api/auth/user/info/"

        try:
            response = requests.get(
                url,
                headers=self._get_auth_headers(),
            )

            if response.status_code == 200:
                user_info: Dict[str, Any] = response.json()
                self.user_info = user_info
                return self.user_info
            else:
                raise DataSpaceAuthError(
                    "Failed to get user info",
                    status_code=response.status_code,
                    response=response.json(),
                )
        except requests.RequestException as e:
            raise DataSpaceAuthError(f"Network error getting user info: {str(e)}")

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    def is_authenticated(self) -> bool:
        """Check if the client is authenticated."""
        return self.access_token is not None

    def ensure_authenticated(self) -> None:
        """
        Ensure the client is authenticated, attempting auto-relogin if needed.

        Raises:
            DataSpaceAuthError: If unable to authenticate
        """
        if not self.is_authenticated():
            # Try to relogin with stored credentials
            if self._username and self._password:
                self.login(self._username, self._password)
            else:
                raise DataSpaceAuthError("Not authenticated. Please call login() first.")

    def get_valid_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            Valid access token

        Raises:
            DataSpaceAuthError: If unable to get valid token
        """
        # First ensure we have a valid Keycloak token
        if self.keycloak_url and self.keycloak_realm:
            keycloak_token = self._ensure_valid_keycloak_token()
            # Re-login to backend with fresh Keycloak token if needed
            if not self.access_token:
                self._login_with_keycloak_token(keycloak_token)

        if not self.access_token:
            raise DataSpaceAuthError("No access token available")

        return self.access_token
