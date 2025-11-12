"""Tests for AI model resource client."""

import unittest
from unittest.mock import MagicMock, patch

from dataspace_sdk.resources.aimodels import AIModelClient


class TestAIModelClient(unittest.TestCase):
    """Test cases for AIModelClient."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.base_url = "https://api.test.com"
        self.auth_client = MagicMock()
        self.client = AIModelClient(self.base_url, self.auth_client)

    def test_init(self) -> None:
        """Test AIModelClient initialization."""
        self.assertEqual(self.client.base_url, self.base_url)
        self.assertEqual(self.client.auth_client, self.auth_client)

    @patch.object(AIModelClient, "get")
    def test_search_models(self, mock_get: MagicMock) -> None:
        """Test AI model search."""
        mock_get.return_value = {
            "total": 5,
            "results": [{"id": "1", "displayName": "Test Model", "modelType": "LLM"}],
        }

        result = self.client.search(query="test", page=1, page_size=10)

        self.assertEqual(result["total"], 5)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["displayName"], "Test Model")
        mock_get.assert_called_once()

    @patch.object(AIModelClient, "get")
    def test_get_model_by_id(self, mock_get: MagicMock) -> None:
        """Test get AI model by ID."""
        mock_get.return_value = {
            "id": "123",
            "displayName": "Test Model",
            "modelType": "LLM",
            "provider": "OpenAI",
        }

        result = self.client.get_by_id("123")

        self.assertEqual(result["id"], "123")
        self.assertEqual(result["displayName"], "Test Model")
        mock_get.assert_called_once()

    @patch.object(AIModelClient, "post")
    def test_get_model_by_id_graphql(self, mock_post: MagicMock) -> None:
        """Test get AI model by ID using GraphQL."""
        mock_post.return_value = {
            "data": {
                "aiModel": {
                    "id": "123",
                    "displayName": "Test Model",
                    "description": "A test model",
                }
            }
        }

        result = self.client.get_by_id_graphql("123")

        self.assertEqual(result["id"], "123")
        self.assertEqual(result["displayName"], "Test Model")
        mock_post.assert_called_once()

    @patch.object(AIModelClient, "post")
    def test_list_all_models(self, mock_post: MagicMock) -> None:
        """Test list all AI models."""
        mock_post.return_value = {"data": {"aiModels": [{"id": "1", "displayName": "Model 1"}]}}

        result = self.client.list_all(limit=10, offset=0)

        self.assertIsInstance(result, (list, dict))
        mock_post.assert_called_once()

    @patch.object(AIModelClient, "post")
    def test_get_organization_models(self, mock_post: MagicMock) -> None:
        """Test get organization AI models."""
        mock_post.return_value = {"data": {"aiModels": [{"id": "1", "name": "Org Model"}]}}

        result = self.client.get_organization_models("org-123", limit=10)

        self.assertIsInstance(result, (list, dict))
        mock_post.assert_called_once()

    @patch.object(AIModelClient, "get")
    def test_search_with_filters(self, mock_get: MagicMock) -> None:
        """Test AI model search with filters."""
        mock_get.return_value = {"total": 3, "results": []}

        result = self.client.search(
            query="language",
            tags=["nlp"],
            sectors=["tech"],
            model_type="LLM",
            provider="OpenAI",
            status="ACTIVE",
        )

        self.assertEqual(result["total"], 3)
        mock_get.assert_called_once()

    @patch.object(AIModelClient, "post")
    def test_graphql_error_handling(self, mock_post: MagicMock) -> None:
        """Test GraphQL error handling."""
        from dataspace_sdk.exceptions import DataSpaceAPIError

        mock_post.return_value = {"errors": [{"message": "GraphQL error"}]}

        with self.assertRaises(DataSpaceAPIError):
            self.client.get_by_id_graphql("123")


if __name__ == "__main__":
    unittest.main()
