"""Main DataSpace SDK client."""

from typing import Optional

from dataspace_sdk.auth import AuthClient
from dataspace_sdk.resources.aimodels import AIModelClient
from dataspace_sdk.resources.datasets import DatasetClient
from dataspace_sdk.resources.usecases import UseCaseClient


class DataSpaceClient:
    """
    Main client for interacting with DataSpace API.

    Example:
        >>> from dataspace_sdk import DataSpaceClient
        >>>
        >>> # Initialize client
        >>> client = DataSpaceClient(base_url="https://api.dataspace.example.com")
        >>>
        >>> # Login with Keycloak token
        >>> client.login(keycloak_token="your_keycloak_token")
        >>>
        >>> # Search for datasets
        >>> datasets = client.datasets.search(query="health", tags=["public-health"])
        >>>
        >>> # Get a specific dataset
        >>> dataset = client.datasets.get_by_id("dataset-uuid")
        >>>
        >>> # Get organization's resources
        >>> org_datasets = client.datasets.get_organization_datasets("org-uuid")
        >>> org_models = client.aimodels.get_organization_models("org-uuid")
        >>> org_usecases = client.usecases.get_organization_usecases("org-uuid")
    """

    def __init__(self, base_url: str):
        """
        Initialize the DataSpace client.

        Args:
            base_url: Base URL of the DataSpace API (e.g., "https://api.dataspace.example.com")
        """
        self.base_url = base_url.rstrip("/")
        self._auth = AuthClient(self.base_url)

        # Initialize resource clients
        self.datasets = DatasetClient(self.base_url, self._auth)
        self.aimodels = AIModelClient(self.base_url, self._auth)
        self.usecases = UseCaseClient(self.base_url, self._auth)

    def login(self, keycloak_token: str) -> dict:
        """
        Login using a Keycloak token.

        Args:
            keycloak_token: Valid Keycloak access token

        Returns:
            Dictionary containing user info and tokens

        Raises:
            DataSpaceAuthError: If authentication fails

        Example:
            >>> client = DataSpaceClient(base_url="https://api.dataspace.example.com")
            >>> user_info = client.login(keycloak_token="your_token")
            >>> print(user_info["user"]["username"])
        """
        return self._auth.login_with_keycloak(keycloak_token)

    def refresh_token(self) -> str:
        """
        Refresh the access token using the refresh token.

        Returns:
            New access token

        Raises:
            DataSpaceAuthError: If token refresh fails

        Example:
            >>> client.refresh_token()
        """
        return self._auth.refresh_access_token()

    def get_user_info(self) -> dict:
        """
        Get current user information.

        Returns:
            Dictionary containing user information including organizations

        Raises:
            DataSpaceAuthError: If not authenticated or request fails

        Example:
            >>> user_info = client.get_user_info()
            >>> print(user_info["organizations"])
        """
        return self._auth.get_user_info()

    def is_authenticated(self) -> bool:
        """
        Check if the client is authenticated.

        Returns:
            True if authenticated, False otherwise

        Example:
            >>> if client.is_authenticated():
            ...     datasets = client.datasets.search()
        """
        return self._auth.is_authenticated()

    @property
    def user(self) -> Optional[dict]:
        """
        Get cached user information.

        Returns:
            User information dictionary or None if not authenticated
        """
        return self._auth.user_info

    @property
    def access_token(self) -> Optional[str]:
        """
        Get the current access token.

        Returns:
            Access token string or None if not authenticated
        """
        return self._auth.access_token
