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

    @patch.object(AIModelClient, "_make_request")
    def test_search_models(self, mock_request: MagicMock) -> None:
        """Test AI model search."""
        mock_request.return_value = {
            "total": 5,
            "results": [{"id": "1", "displayName": "Test Model", "modelType": "LLM"}],
        }

        result = self.client.search(query="test", page=1, page_size=10)

        self.assertEqual(result["total"], 5)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["displayName"], "Test Model")
        mock_request.assert_called_once()

    @patch.object(AIModelClient, "_make_request")
    def test_get_model_by_id(self, mock_request: MagicMock) -> None:
        """Test get AI model by ID."""
        mock_request.return_value = {
            "id": "123",
            "displayName": "Test Model",
            "modelType": "LLM",
            "provider": "OpenAI",
        }

        result = self.client.get_by_id("123")

        self.assertEqual(result["id"], "123")
        self.assertEqual(result["displayName"], "Test Model")
        mock_request.assert_called_once()

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

    @patch.object(AIModelClient, "_make_request")
    def test_search_with_filters(self, mock_request: MagicMock) -> None:
        """Test AI model search with filters."""
        mock_request.return_value = {"total": 3, "results": []}

        result = self.client.search(
            query="language",
            tags=["nlp"],
            sectors=["tech"],
            status="ACTIVE",
            model_type="LLM",
            provider="OpenAI",
        )

        self.assertEqual(result["total"], 3)
        mock_request.assert_called_once()

    @patch.object(AIModelClient, "_make_request")
    def test_graphql_error_handling(self, mock_request: MagicMock) -> None:
        """Test GraphQL error handling."""
        from dataspace_sdk.exceptions import DataSpaceAPIError

        mock_request.return_value = {"errors": [{"message": "GraphQL error"}]}

        with self.assertRaises(DataSpaceAPIError):
            self.client.get_by_id_graphql("123")

    @patch.object(AIModelClient, "_make_request")
    def test_call_model(self, mock_request: MagicMock) -> None:
        """Test calling an AI model."""
        mock_request.return_value = {
            "success": True,
            "output": "Paris is the capital of France.",
            "latency_ms": 150,
            "provider": "OpenAI",
        }

        result = self.client.call_model(
            model_id="123",
            input_text="What is the capital of France?",
            parameters={"temperature": 0.7, "max_tokens": 100},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["output"], "Paris is the capital of France.")
        self.assertEqual(result["latency_ms"], 150)
        mock_request.assert_called_once()

    @patch.object(AIModelClient, "_make_request")
    def test_call_model_async(self, mock_request: MagicMock) -> None:
        """Test calling an AI model asynchronously."""
        mock_request.return_value = {
            "task_id": "task-456",
            "status": "PENDING",
            "created_at": "2024-01-01T00:00:00Z",
        }

        result = self.client.call_model_async(
            model_id="123",
            input_text="Generate a long document",
            parameters={"max_tokens": 2000},
        )

        self.assertEqual(result["task_id"], "task-456")
        self.assertEqual(result["status"], "PENDING")
        mock_request.assert_called_once()

    @patch.object(AIModelClient, "_make_request")
    def test_call_model_error(self, mock_request: MagicMock) -> None:
        """Test AI model call with error."""
        mock_request.return_value = {
            "success": False,
            "error": "Model not available",
        }

        result = self.client.call_model(
            model_id="123",
            input_text="Test input",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Model not available")

    @patch.object(AIModelClient, "_make_request")
    def test_create_model(self, mock_request: MagicMock) -> None:
        """Test creating an AI model."""
        mock_request.return_value = {
            "id": "new-model-123",
            "displayName": "New Model",
            "modelType": "LLM",
        }

        result = self.client.create(
            {
                "displayName": "New Model",
                "modelType": "LLM",
                "provider": "OpenAI",
            }
        )

        self.assertEqual(result["id"], "new-model-123")
        self.assertEqual(result["displayName"], "New Model")
        mock_request.assert_called_once()

    @patch.object(AIModelClient, "_make_request")
    def test_update_model(self, mock_request: MagicMock) -> None:
        """Test updating an AI model."""
        mock_request.return_value = {
            "id": "123",
            "displayName": "Updated Model",
            "description": "Updated description",
        }

        result = self.client.update(
            "123", {"displayName": "Updated Model", "description": "Updated description"}
        )

        self.assertEqual(result["displayName"], "Updated Model")
        mock_request.assert_called_once()

    @patch.object(AIModelClient, "_make_request")
    def test_delete_model(self, mock_request: MagicMock) -> None:
        """Test deleting an AI model."""
        mock_request.return_value = {"message": "Model deleted successfully"}

        result = self.client.delete_model("123")

        self.assertEqual(result["message"], "Model deleted successfully")
        mock_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
