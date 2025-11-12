"""Tests for dataset resource client."""

import unittest
from unittest.mock import MagicMock, patch

from dataspace_sdk.resources.datasets import DatasetClient


class TestDatasetClient(unittest.TestCase):
    """Test cases for DatasetClient."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.base_url = "https://api.test.com"
        self.auth_client = MagicMock()
        self.client = DatasetClient(self.base_url, self.auth_client)

    def test_init(self) -> None:
        """Test DatasetClient initialization."""
        self.assertEqual(self.client.base_url, self.base_url)
        self.assertEqual(self.client.auth_client, self.auth_client)

    @patch.object(DatasetClient, "get")
    def test_search_datasets(self, mock_get: MagicMock) -> None:
        """Test dataset search."""
        mock_get.return_value = {
            "total": 10,
            "results": [{"id": "1", "title": "Test Dataset"}],
        }

        result = self.client.search(query="test", page=1, page_size=10)

        self.assertEqual(result["total"], 10)
        self.assertEqual(len(result["results"]), 1)
        mock_get.assert_called_once()

    @patch.object(DatasetClient, "post")
    def test_get_dataset_by_id(self, mock_post: MagicMock) -> None:
        """Test get dataset by ID."""
        mock_post.return_value = {"data": {"dataset": {"id": "123", "title": "Test Dataset"}}}

        result = self.client.get_by_id("123")

        self.assertEqual(result["id"], "123")
        self.assertEqual(result["title"], "Test Dataset")

    @patch.object(DatasetClient, "post")
    def test_list_all_datasets(self, mock_post: MagicMock) -> None:
        """Test list all datasets."""
        mock_post.return_value = {"data": {"datasets": [{"id": "1", "title": "Dataset 1"}]}}

        result = self.client.list_all(limit=10, offset=0)

        self.assertIsInstance(result, (list, dict))

    @patch.object(DatasetClient, "get")
    def test_get_trending_datasets(self, mock_get: MagicMock) -> None:
        """Test get trending datasets."""
        mock_get.return_value = {"results": [{"id": "1", "title": "Trending Dataset"}]}

        result = self.client.get_trending(limit=5)

        self.assertIn("results", result)
        mock_get.assert_called_once()

    @patch.object(DatasetClient, "post")
    def test_get_organization_datasets(self, mock_post: MagicMock) -> None:
        """Test get organization datasets."""
        mock_post.return_value = {"data": {"datasets": [{"id": "1", "title": "Org Dataset"}]}}

        result = self.client.get_organization_datasets("org-123", limit=10)

        self.assertIsInstance(result, (list, dict))
        mock_post.assert_called_once()

    @patch.object(DatasetClient, "get")
    def test_search_with_filters(self, mock_get: MagicMock) -> None:
        """Test dataset search with filters."""
        mock_get.return_value = {"total": 5, "results": []}

        result = self.client.search(
            query="health",
            tags=["public-health"],
            sectors=["health"],
            status="PUBLISHED",
            access_type="OPEN",
        )

        self.assertEqual(result["total"], 5)
        mock_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
