"""Authentication module for DataSpace SDK."""

from typing import Any, Dict, Optional

import requests

from dataspace_sdk.exceptions import DataSpaceAuthError


class AuthClient:
    """Handles authentication with DataSpace API."""

    def __init__(self, base_url: str):
        """
        Initialize the authentication client.

        Args:
            base_url: Base URL of the DataSpace API
        """
        self.base_url = base_url.rstrip("/")
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.user_info: Optional[Dict] = None

    def login_with_keycloak(self, keycloak_token: str) -> Dict[str, Any]:
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
