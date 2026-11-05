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

    @patch.object(DatasetClient, "_make_request")
    def test_search_datasets(self, mock_request: MagicMock) -> None:
        """Test dataset search."""
        mock_request.return_value = {
            "total": 10,
            "results": [{"id": "1", "title": "Test Dataset"}],
        }

        result = self.client.search(query="test", page=1, page_size=10)

        self.assertEqual(result["total"], 10)
        self.assertEqual(len(result["results"]), 1)
        mock_request.assert_called_once()

    @patch.object(DatasetClient, "_make_request")
    def test_get_dataset_by_id(self, mock_request: MagicMock) -> None:
        """Test get dataset by ID."""
        mock_request.return_value = {"data": {"getDataset": {"id": "123", "title": "Test Dataset"}}}

        result = self.client.get_by_id("123")

        self.assertEqual(result["id"], "123")
        self.assertEqual(result["title"], "Test Dataset")

    @patch.object(DatasetClient, "_make_request")
    def test_list_all_datasets(self, mock_request: MagicMock) -> None:
        """Test list all datasets."""
        mock_request.return_value = {"data": {"datasets": [{"id": "1", "title": "Dataset 1"}]}}

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

    @patch.object(DatasetClient, "_make_request")
    def test_search_with_filters(self, mock_request: MagicMock) -> None:
        """Test dataset search with filters."""
        mock_request.return_value = {"total": 5, "results": []}

        result = self.client.search(
            query="health",
            tags=["public-health"],
            sectors=["health"],
            status="PUBLISHED",
            access_type="OPEN",
        )

        self.assertEqual(result["total"], 5)
        mock_request.assert_called_once()

    @patch.object(DatasetClient, "_make_request")
    def test_get_dataset_with_resources(self, mock_request: MagicMock) -> None:
        """Test get dataset by ID which includes resources."""
        mock_request.return_value = {
            "data": {
                "getDataset": {
                    "id": "dataset-123",
                    "title": "Test Dataset",
                    "resources": [
                        {
                            "id": "res-1",
                            "title": "Resource 1",
                            "fileDetails": {"format": "CSV"},
                        }
                    ],
                }
            }
        }

        result = self.client.get_by_id("dataset-123")

        self.assertEqual(result["id"], "dataset-123")
        self.assertEqual(len(result["resources"]), 1)
        self.assertEqual(result["resources"][0]["title"], "Resource 1")
        mock_request.assert_called_once()

    @patch.object(DatasetClient, "list_all")
    def test_get_organization_datasets(self, mock_list_all: MagicMock) -> None:
        """Test get datasets by organization."""
        mock_list_all.return_value = [
            {"id": "1", "title": "Org Dataset 1"},
            {"id": "2", "title": "Org Dataset 2"},
        ]

        result = self.client.get_organization_datasets("org-123", limit=10)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        mock_list_all.assert_called_once_with(organization_id="org-123", limit=10, offset=0)

    @patch.object(DatasetClient, "_make_request")
    def test_search_with_sorting(self, mock_request: MagicMock) -> None:
        """Test dataset search with sorting."""
        mock_request.return_value = {"total": 3, "results": []}

        result = self.client.search(query="test", sort="recent", page=1, page_size=10)

        self.assertEqual(result["total"], 3)
        mock_request.assert_called_once()


class TestDatasetClientDataFetch(unittest.TestCase):
    """Tests for indexed-data fetch methods on DatasetClient."""

    def setUp(self) -> None:
        self.client = DatasetClient("https://api.test.com", MagicMock())

    def test_build_data_params_basic(self) -> None:
        params = DatasetClient._build_data_params(
            filters=None,
            columns=None,
            order_by=None,
            limit=50,
            offset=10,
            count=True,
        )
        self.assertEqual(params["limit"], 50)
        self.assertEqual(params["offset"], 10)
        self.assertEqual(params["count"], "true")
        self.assertNotIn("columns", params)

    def test_build_data_params_filters_and_lists(self) -> None:
        params = DatasetClient._build_data_params(
            filters={"price__gte": 10, "tag__in": ["a", "b"], "active": True},
            columns=["id", "name"],
            order_by=["-price", "name"],
            limit=100,
            offset=0,
            count=False,
        )
        self.assertEqual(params["columns"], "id,name")
        self.assertEqual(params["order_by"], "-price,name")
        self.assertEqual(params["count"], "false")
        self.assertEqual(params["price__gte"], 10)
        self.assertEqual(params["tag__in"], ["a", "b"])
        self.assertEqual(params["active"], "true")

    @patch.object(DatasetClient, "get")
    def test_get_resource_data(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {
            "columns": ["id"],
            "rows": [[1]],
            "total": 1,
            "limit": 100,
            "offset": 0,
        }
        result = self.client.get_resource_data(
            "res-1",
            filters={"id__gte": 1},
            columns=["id"],
            order_by=["id"],
            limit=10,
        )
        self.assertEqual(result["total"], 1)
        endpoint, kwargs = mock_get.call_args[0][0], mock_get.call_args.kwargs
        self.assertEqual(endpoint, "/api/resources/res-1/data/")
        self.assertEqual(kwargs["params"]["columns"], "id")
        self.assertEqual(kwargs["params"]["id__gte"], 1)

    @patch.object(DatasetClient, "get")
    def test_get_dataset_data_with_resource_id(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {"rows": [], "columns": [], "total": 0}
        self.client.get_dataset_data("ds-1", resource_id="res-9", limit=5)
        endpoint = mock_get.call_args[0][0]
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(endpoint, "/api/datasets/ds-1/data/")
        self.assertEqual(params["resource_id"], "res-9")
        self.assertEqual(params["limit"], 5)

    @patch.object(DatasetClient, "get")
    def test_get_prompt_data_shorthands(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {"rows": [], "columns": [], "total": 0}
        self.client.get_prompt_data(
            "ds-1",
            prompt_contains="translate",
            response_contains="hello",
            min_length=5,
            max_length=100,
        )
        endpoint = mock_get.call_args[0][0]
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(endpoint, "/api/datasets/ds-1/prompts/")
        self.assertEqual(params["prompt_contains"], "translate")
        self.assertEqual(params["response_contains"], "hello")
        self.assertEqual(params["min_length"], 5)
        self.assertEqual(params["max_length"], 100)

    @patch.object(DatasetClient, "get_resource_data")
    def test_iter_resource_data_paginates(self, mock_get_data: MagicMock) -> None:
        # Two pages: full batch then partial page (terminator)
        mock_get_data.side_effect = [
            {"columns": ["id", "name"], "rows": [[1, "a"], [2, "b"]]},
            {"columns": ["id", "name"], "rows": [[3, "c"]]},
        ]
        rows = list(self.client.iter_resource_data("res-1", batch_size=2))
        self.assertEqual(
            rows,
            [
                {"id": 1, "name": "a"},
                {"id": 2, "name": "b"},
                {"id": 3, "name": "c"},
            ],
        )
        self.assertEqual(mock_get_data.call_count, 2)
        # Second call advances offset
        self.assertEqual(mock_get_data.call_args_list[1].kwargs["offset"], 2)

    @patch.object(DatasetClient, "get_resource_data")
    def test_iter_resource_data_empty(self, mock_get_data: MagicMock) -> None:
        mock_get_data.return_value = {"columns": ["id"], "rows": []}
        self.assertEqual(list(self.client.iter_resource_data("res-1")), [])


if __name__ == "__main__":
    unittest.main()
