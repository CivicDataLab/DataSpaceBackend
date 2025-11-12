"""Tests for authentication module."""

import unittest
from unittest.mock import MagicMock, patch

from dataspace_sdk.auth import AuthClient
from dataspace_sdk.exceptions import DataSpaceAuthError


class TestAuthClient(unittest.TestCase):
    """Test cases for AuthClient."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.base_url = "https://api.test.com"
        self.auth_client = AuthClient(self.base_url)

    def test_init(self) -> None:
        """Test AuthClient initialization."""
        self.assertEqual(self.auth_client.base_url, self.base_url)
        self.assertIsNone(self.auth_client.access_token)
        self.assertIsNone(self.auth_client.refresh_token)
        self.assertIsNone(self.auth_client.user_info)

    @patch("dataspace_sdk.auth.requests.post")
    def test_login_success(self, mock_post: MagicMock) -> None:
        """Test successful login."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access": "test_access_token",
            "refresh": "test_refresh_token",
            "user": {"id": "123", "username": "testuser"},
        }
        mock_post.return_value = mock_response

        result = self.auth_client.login_with_keycloak("test_keycloak_token")

        self.assertEqual(self.auth_client.access_token, "test_access_token")
        self.assertEqual(self.auth_client.refresh_token, "test_refresh_token")
        self.assertIsNotNone(self.auth_client.user_info)
        self.assertEqual(result["user"]["username"], "testuser")

    @patch("dataspace_sdk.auth.requests.post")
    def test_login_failure(self, mock_post: MagicMock) -> None:
        """Test failed login."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Invalid token"}
        mock_post.return_value = mock_response

        with self.assertRaises(DataSpaceAuthError):
            self.auth_client.login_with_keycloak("invalid_token")

    @patch("dataspace_sdk.auth.requests.post")
    def test_refresh_token_success(self, mock_post: MagicMock) -> None:
        """Test successful token refresh."""
        self.auth_client.refresh_token = "test_refresh_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access": "new_access_token"}
        mock_post.return_value = mock_response

        result = self.auth_client.refresh_access_token()

        self.assertEqual(result, "new_access_token")
        self.assertEqual(self.auth_client.access_token, "new_access_token")

    def test_refresh_token_no_refresh_token(self) -> None:
        """Test token refresh without refresh token."""
        with self.assertRaises(DataSpaceAuthError):
            self.auth_client.refresh_access_token()

    @patch("dataspace_sdk.auth.requests.get")
    def test_get_user_info_success(self, mock_get: MagicMock) -> None:
        """Test successful user info retrieval."""
        self.auth_client.access_token = "test_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"user": {"id": "123", "username": "testuser"}}
        mock_get.return_value = mock_response

        result = self.auth_client.get_user_info()

        self.assertIsNotNone(result)
        self.assertEqual(result["user"]["username"], "testuser")

    def test_get_user_info_not_authenticated(self) -> None:
        """Test user info retrieval without authentication."""
        with self.assertRaises(DataSpaceAuthError):
            self.auth_client.get_user_info()

    def test_is_authenticated(self) -> None:
        """Test authentication status check."""
        self.assertFalse(self.auth_client.is_authenticated())

        self.auth_client.access_token = "test_token"
        self.assertTrue(self.auth_client.is_authenticated())


if __name__ == "__main__":
    unittest.main()
