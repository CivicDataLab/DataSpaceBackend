"""Tests for main DataSpace client."""

import unittest
from unittest.mock import MagicMock, patch

from dataspace_sdk.client import DataSpaceClient


class TestDataSpaceClient(unittest.TestCase):
    """Test cases for DataSpaceClient."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.base_url = "https://api.test.com"
        self.client = DataSpaceClient(self.base_url)

    def test_init(self) -> None:
        """Test DataSpaceClient initialization."""
        self.assertEqual(self.client.base_url, self.base_url)
        self.assertIsNotNone(self.client._auth)
        self.assertIsNotNone(self.client.datasets)
        self.assertIsNotNone(self.client.aimodels)
        self.assertIsNotNone(self.client.usecases)

    @patch("dataspace_sdk.client.AuthClient.login")
    def test_login(self, mock_login: MagicMock) -> None:
        """Test login method with username/password."""
        mock_login.return_value = {
            "access": "token",
            "user": {"id": "123", "username": "testuser"},
        }

        result = self.client.login("testuser", "password")

        self.assertEqual(result["user"]["username"], "testuser")
        mock_login.assert_called_once_with("testuser", "password")

    @patch("dataspace_sdk.client.AuthClient._login_with_keycloak_token")
    def test_login_with_token(self, mock_login: MagicMock) -> None:
        """Test login method with Keycloak token."""
        mock_login.return_value = {
            "access": "token",
            "user": {"id": "123", "username": "testuser"},
        }

        result = self.client.login_with_token("test_token")

        self.assertEqual(result["user"]["username"], "testuser")
        mock_login.assert_called_once_with("test_token")

    @patch("dataspace_sdk.client.AuthClient.refresh_access_token")
    def test_refresh_token(self, mock_refresh: MagicMock) -> None:
        """Test token refresh."""
        mock_refresh.return_value = "new_token"

        result = self.client.refresh_token()

        self.assertEqual(result, "new_token")
        mock_refresh.assert_called_once()

    @patch("dataspace_sdk.client.AuthClient.get_user_info")
    def test_get_user_info(self, mock_get_info: MagicMock) -> None:
        """Test get user info."""
        mock_get_info.return_value = {"user": {"id": "123"}}

        result = self.client.get_user_info()

        self.assertEqual(result["user"]["id"], "123")
        mock_get_info.assert_called_once()

    def test_is_authenticated(self) -> None:
        """Test authentication status."""
        self.client._auth.is_authenticated = MagicMock(return_value=False)
        self.assertFalse(self.client.is_authenticated())

        self.client._auth.is_authenticated = MagicMock(return_value=True)
        self.assertTrue(self.client.is_authenticated())

    def test_user_property(self) -> None:
        """Test user property."""
        self.client._auth.user_info = {"id": "123", "username": "testuser"}
        self.assertEqual(self.client.user["username"], "testuser")

        self.client._auth.user_info = None
        self.assertIsNone(self.client.user)


if __name__ == "__main__":
    unittest.main()
