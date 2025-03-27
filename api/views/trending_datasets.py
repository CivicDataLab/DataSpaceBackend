import structlog
from django.http import HttpRequest
from elasticsearch_dsl import Search
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.utils.telemetry_utils import trace_method, track_metrics
from api.views.search_dataset import DatasetDocumentSerializer, SearchDataset
from search.documents import DatasetDocument

logger = structlog.get_logger(__name__)


class TrendingDatasets(SearchDataset):
    """
    View for retrieving trending datasets.

    This endpoint returns datasets sorted by their trending score,
    which is calculated based on download count and recency of downloads.
    """

    serializer_class = DatasetDocumentSerializer
    document_class = DatasetDocument
    permission_classes = [AllowAny]

    @trace_method(name="get", attributes={"component": "trending_datasets"})
    @track_metrics(name="trending_datasets_view")
    def get(self, request: HttpRequest) -> Response:
        """
        Get trending datasets.

        Returns datasets sorted by trending score in descending order.
        Supports all the same filtering capabilities as the regular search endpoint.
        """
        # Create a mutable copy of the query parameters
        self._trending_params = {
            "sort": "trending",
            "order": "desc",
            "limit": request.GET.get("limit", "10"),
        }

        # Use the parent class method to handle the request
        return super().get(request)

    def get_search(self) -> Search:
        """Override get_search to apply trending parameters."""
        # Get the base search from the parent class
        search = super().get_search()

        # Apply trending parameters if they exist
        if hasattr(self, "_trending_params"):
            # Apply sort
            search = self.add_sort(
                self._trending_params.get("sort", "trending"),
                search,
                self._trending_params.get("order", "desc"),
            )

        # Add filter for trending score > 0
        search = search.filter("range", trending_score={"gt": 0})

        return search  # type: ignore
