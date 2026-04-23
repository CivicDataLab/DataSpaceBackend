"""Tests for use case resource client."""

import unittest
from unittest.mock import MagicMock, patch

from dataspace_sdk.resources.usecases import UseCaseClient


class TestUseCaseClient(unittest.TestCase):
    """Test cases for UseCaseClient."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.base_url = "https://api.test.com"
        self.auth_client = MagicMock()
        self.client = UseCaseClient(self.base_url, self.auth_client)

    def test_init(self) -> None:
        """Test UseCaseClient initialization."""
        self.assertEqual(self.client.base_url, self.base_url)
        self.assertEqual(self.client.auth_client, self.auth_client)

    @patch.object(UseCaseClient, "_make_request")
    def test_search_usecases(self, mock_request: MagicMock) -> None:
        """Test use case search."""
        mock_request.return_value = {
            "total": 8,
            "results": [
                {
                    "id": 1,
                    "title": "Test Use Case",
                    "status": "PUBLISHED",
                    "running_status": "COMPLETED",
                }
            ],
        }

        result = self.client.search(query="test", page=1, page_size=10)

        self.assertEqual(result["total"], 8)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["title"], "Test Use Case")
        mock_request.assert_called_once()

    @patch.object(UseCaseClient, "post")
    def test_get_usecase_by_id(self, mock_post: MagicMock) -> None:
        """Test get use case by ID."""
        mock_post.return_value = {
            "data": {
                "useCase": {
                    "id": 123,
                    "title": "Test Use Case",
                    "summary": "A test use case",
                    "status": "PUBLISHED",
                }
            }
        }

        result = self.client.get_by_id(123)

        self.assertEqual(result["id"], 123)
        self.assertEqual(result["title"], "Test Use Case")
        mock_post.assert_called_once()

    @patch.object(UseCaseClient, "post")
    def test_list_all_usecases(self, mock_post: MagicMock) -> None:
        """Test list all use cases."""
        mock_post.return_value = {"data": {"useCases": [{"id": 1, "title": "Use Case 1"}]}}

        result = self.client.list_all(limit=10, offset=0)

        self.assertIsInstance(result, (list, dict))
        mock_post.assert_called_once()

    @patch.object(UseCaseClient, "post")
    def test_get_organization_usecases(self, mock_post: MagicMock) -> None:
        """Test get organization use cases."""
        mock_post.return_value = {"data": {"useCases": [{"id": 1, "title": "Org Use Case"}]}}

        result = self.client.get_organization_usecases("org-123", limit=10)

        self.assertIsInstance(result, (list, dict))
        mock_post.assert_called_once()

    @patch.object(UseCaseClient, "_make_request")
    def test_search_with_filters(self, mock_request: MagicMock) -> None:
        """Test use case search with filters."""
        mock_request.return_value = {"total": 4, "results": []}

        result = self.client.search(
            query="monitoring",
            tags=["monitoring"],
            sectors=["governance"],
            status="PUBLISHED",
            running_status="COMPLETED",
        )

        self.assertEqual(result["total"], 4)
        mock_request.assert_called_once()

    @patch.object(UseCaseClient, "_make_request")
    def test_search_with_sorting(self, mock_request: MagicMock) -> None:
        """Test use case search with sorting."""
        mock_request.return_value = {"total": 2, "results": []}

        result = self.client.search(query="test", sort="completed_on", page=1, page_size=10)

        self.assertEqual(result["total"], 2)
        mock_request.assert_called_once()

    @patch.object(UseCaseClient, "post")
    def test_graphql_error_handling(self, mock_post: MagicMock) -> None:
        """Test GraphQL error handling."""
        from dataspace_sdk.exceptions import DataSpaceAPIError

        mock_post.return_value = {"errors": [{"message": "GraphQL error"}]}

        with self.assertRaises(DataSpaceAPIError):
            self.client.get_by_id(123)

    @patch.object(UseCaseClient, "_make_request")
    def test_search_pagination(self, mock_request: MagicMock) -> None:
        """Test use case search with pagination."""
        mock_request.return_value = {"total": 50, "results": [], "page": 2, "page_size": 20}

        result = self.client.search(query="test", page=2, page_size=20)

        self.assertEqual(result["total"], 50)
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["page_size"], 20)
        mock_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
