"""Tests for base API client."""

import unittest
from unittest.mock import MagicMock, patch

from dataspace_sdk.base import BaseAPIClient
from dataspace_sdk.exceptions import (
    DataSpaceAPIError,
    DataSpaceAuthError,
    DataSpaceNotFoundError,
    DataSpaceValidationError,
)


class TestBaseAPIClient(unittest.TestCase):
    """Test cases for BaseAPIClient."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.base_url = "https://api.test.com"
        self.client = BaseAPIClient(self.base_url)

    def test_init(self) -> None:
        """Test BaseAPIClient initialization."""
        self.assertEqual(self.client.base_url, self.base_url)
        self.assertIsNone(self.client.auth_client)

    def test_get_headers_no_auth(self) -> None:
        """Test header generation without authentication."""
        headers = self.client._get_headers()
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertNotIn("Authorization", headers)

    def test_get_headers_with_auth(self) -> None:
        """Test header generation with authentication."""
        mock_auth = MagicMock()
        mock_auth.is_authenticated.return_value = True
        mock_auth.access_token = "test_token"
        self.client.auth_client = mock_auth

        headers = self.client._get_headers()
        self.assertEqual(headers["Authorization"], "Bearer test_token")

    @patch("dataspace_sdk.base.requests.request")
    def test_make_request_success_200(self, mock_request: MagicMock) -> None:
        """Test successful request with 200 status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"data": "test"}'
        mock_response.json.return_value = {"data": "test"}
        mock_request.return_value = mock_response

        result = self.client._make_request("GET", "/test")
        self.assertEqual(result["data"], "test")

    @patch("dataspace_sdk.base.requests.request")
    def test_make_request_success_204(self, mock_request: MagicMock) -> None:
        """Test successful request with 204 status."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_request.return_value = mock_response

        result = self.client._make_request("DELETE", "/test")
        self.assertEqual(result, {})

    @patch("dataspace_sdk.base.requests.request")
    def test_make_request_401_error(self, mock_request: MagicMock) -> None:
        """Test request with 401 authentication error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.content = b'{"error": "Unauthorized"}'
        mock_response.json.return_value = {"error": "Unauthorized"}
        mock_request.return_value = mock_response

        with self.assertRaises(DataSpaceAuthError):
            self.client._make_request("GET", "/test")

    @patch("dataspace_sdk.base.requests.request")
    def test_make_request_404_error(self, mock_request: MagicMock) -> None:
        """Test request with 404 not found error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.content = b'{"error": "Not found"}'
        mock_response.json.return_value = {"error": "Not found"}
        mock_request.return_value = mock_response

        with self.assertRaises(DataSpaceNotFoundError):
            self.client._make_request("GET", "/test")

    @patch("dataspace_sdk.base.requests.request")
    def test_make_request_400_error(self, mock_request: MagicMock) -> None:
        """Test request with 400 validation error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"error": "Validation failed"}'
        mock_response.json.return_value = {"error": "Validation failed"}
        mock_request.return_value = mock_response

        with self.assertRaises(DataSpaceValidationError):
            self.client._make_request("GET", "/test")

    @patch("dataspace_sdk.base.requests.request")
    def test_make_request_500_error(self, mock_request: MagicMock) -> None:
        """Test request with 500 server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b'{"error": "Server error"}'
        mock_response.json.return_value = {"error": "Server error"}
        mock_request.return_value = mock_response

        with self.assertRaises(DataSpaceAPIError):
            self.client._make_request("GET", "/test")

    def test_get_method(self) -> None:
        """Test GET method wrapper."""
        with patch.object(self.client, "_make_request") as mock_request:
            mock_request.return_value = {"data": "test"}
            result = self.client.get("/test", params={"key": "value"})
            mock_request.assert_called_once_with("GET", "/test", params={"key": "value"})
            self.assertEqual(result["data"], "test")

    def test_post_method(self) -> None:
        """Test POST method wrapper."""
        with patch.object(self.client, "_make_request") as mock_request:
            mock_request.return_value = {"data": "test"}
            result = self.client.post("/test", json_data={"key": "value"})
            mock_request.assert_called_once_with(
                "POST", "/test", data=None, json_data={"key": "value"}
            )
            self.assertEqual(result["data"], "test")


if __name__ == "__main__":
    unittest.main()
