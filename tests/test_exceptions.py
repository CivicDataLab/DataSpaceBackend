"""Tests for custom exceptions."""

import unittest

from dataspace_sdk.exceptions import (
    DataSpaceAPIError,
    DataSpaceAuthError,
    DataSpaceNotFoundError,
    DataSpaceValidationError,
)


class TestExceptions(unittest.TestCase):
    """Test cases for custom exceptions."""

    def test_api_error(self) -> None:
        """Test DataSpaceAPIError."""
        error = DataSpaceAPIError("Test error", status_code=500, response={"error": "test"})
        self.assertEqual(error.message, "Test error")
        self.assertEqual(error.status_code, 500)
        self.assertEqual(error.response, {"error": "test"})

    def test_api_error_without_optional_params(self) -> None:
        """Test DataSpaceAPIError without optional parameters."""
        error = DataSpaceAPIError("Test error")
        self.assertEqual(error.message, "Test error")
        self.assertIsNone(error.status_code)
        self.assertIsNone(error.response)

    def test_auth_error(self) -> None:
        """Test DataSpaceAuthError."""
        error = DataSpaceAuthError("Auth failed", status_code=401)
        self.assertEqual(error.message, "Auth failed")
        self.assertEqual(error.status_code, 401)
        self.assertIsInstance(error, DataSpaceAPIError)

    def test_not_found_error(self) -> None:
        """Test DataSpaceNotFoundError."""
        error = DataSpaceNotFoundError("Not found", status_code=404)
        self.assertEqual(error.message, "Not found")
        self.assertEqual(error.status_code, 404)
        self.assertIsInstance(error, DataSpaceAPIError)

    def test_validation_error(self) -> None:
        """Test DataSpaceValidationError."""
        error = DataSpaceValidationError("Validation failed", status_code=400)
        self.assertEqual(error.message, "Validation failed")
        self.assertEqual(error.status_code, 400)
        self.assertIsInstance(error, DataSpaceAPIError)


if __name__ == "__main__":
    unittest.main()
