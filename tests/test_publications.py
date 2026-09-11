"""Tests for the Publication ("Resource") SDK resource client."""

import unittest
from unittest.mock import MagicMock, patch

from dataspace_sdk.resources.publications import PublicationClient


class TestPublicationClient(unittest.TestCase):
    """Test cases for PublicationClient."""

    def setUp(self) -> None:
        self.base_url = "https://api.test.com"
        self.auth_client = MagicMock()
        self.client = PublicationClient(self.base_url, self.auth_client)

    def test_init(self) -> None:
        self.assertEqual(self.client.base_url, self.base_url)
        self.assertEqual(self.client.auth_client, self.auth_client)

    @patch.object(PublicationClient, "_make_request")
    def test_search_hits_the_publication_endpoint(self, mock_request: MagicMock) -> None:
        mock_request.return_value = {"total": 1, "results": [{"id": "1"}]}

        result = self.client.search(
            query="rainfall", resource_type="Report", sectors=["Health"], page=2, page_size=5
        )

        self.assertEqual(result["total"], 1)
        args, kwargs = mock_request.call_args
        self.assertIn("/api/search/publication/", args[1])
        params = kwargs["params"]
        self.assertEqual(params["q"], "rainfall")
        self.assertEqual(params["resource_type"], "Report")
        self.assertEqual(params["sectors"], "Health")
        self.assertEqual(params["page"], 2)

    @patch.object(PublicationClient, "_make_request")
    def test_get_by_id_uses_graphql(self, mock_request: MagicMock) -> None:
        mock_request.return_value = {"data": {"getPublication": {"id": "abc"}}}

        self.client.get_by_id("abc")

        args, kwargs = mock_request.call_args
        self.assertIn("/api/graphql", args[1])
        self.assertEqual(kwargs["json_data"]["variables"]["publicationId"], "abc")

    @patch.object(PublicationClient, "_make_request")
    def test_create_posts_the_mutation(self, mock_request: MagicMock) -> None:
        mock_request.return_value = {"data": {"createPublication": {"success": True}}}

        self.client.create({"title": "New"})

        args, kwargs = mock_request.call_args
        self.assertIn("createPublication", kwargs["json_data"]["query"])
        self.assertEqual(kwargs["json_data"]["variables"]["input"]["title"], "New")

    @patch.object(PublicationClient, "_make_request")
    def test_update_merges_the_id_into_input(self, mock_request: MagicMock) -> None:
        mock_request.return_value = {"data": {"updatePublication": {"success": True}}}

        self.client.update("abc", {"title": "Renamed"})

        args, kwargs = mock_request.call_args
        variables = kwargs["json_data"]["variables"]["input"]
        self.assertEqual(variables["id"], "abc")
        self.assertEqual(variables["title"], "Renamed")

    @patch.object(PublicationClient, "_make_request")
    def test_delete_passes_the_id(self, mock_request: MagicMock) -> None:
        mock_request.return_value = {"data": {"deletePublication": {"success": True}}}

        self.client.delete("abc")

        args, kwargs = mock_request.call_args
        self.assertIn("deletePublication", kwargs["json_data"]["query"])
        self.assertEqual(kwargs["json_data"]["variables"]["publicationId"], "abc")


if __name__ == "__main__":
    unittest.main()
