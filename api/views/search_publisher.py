from typing import Any, Dict, List, Tuple

import structlog
from elasticsearch_dsl import Q as ESQ
from elasticsearch_dsl import Search
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.utils.telemetry_utils import trace_method, track_metrics
from api.views.paginated_elastic_view import PaginatedElasticSearchAPIView
from search.documents import OrganizationPublisherDocument, UserPublisherDocument

logger = structlog.get_logger(__name__)


class PublisherDocumentSerializer(serializers.Serializer):
    """Serializer for Publisher document (both Organization and User)."""

    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    publisher_type = serializers.CharField()  # 'organization' or 'user'
    logo = serializers.CharField(required=False)
    slug = serializers.CharField(required=False)
    created = serializers.DateTimeField(required=False)
    modified = serializers.DateTimeField(required=False)

    # Counts
    published_datasets_count = serializers.IntegerField()
    published_usecases_count = serializers.IntegerField()
    members_count = serializers.IntegerField(required=False)  # Only for organizations
    contributed_sectors_count = serializers.IntegerField()

    # Organization specific fields
    homepage = serializers.CharField(required=False)
    contact_email = serializers.CharField(required=False)
    organization_types = serializers.CharField(required=False)
    github_profile = serializers.CharField(required=False)
    linkedin_profile = serializers.CharField(required=False)
    twitter_profile = serializers.CharField(required=False)
    location = serializers.CharField(required=False)

    # User specific fields
    bio = serializers.CharField(required=False)
    profile_picture = serializers.CharField(required=False)
    username = serializers.CharField(required=False)
    email = serializers.CharField(required=False)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    full_name = serializers.CharField(required=False)

    # Search fields
    sectors = serializers.ListField(required=False)


class SearchPublisher(PaginatedElasticSearchAPIView):
    """API view for searching publishers (organizations and users)."""

    serializer_class = PublisherDocumentSerializer
    permission_classes = [AllowAny]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.logger = structlog.get_logger(__name__)

    def get_document_classes(self) -> List[Any]:
        """Return the document classes to search."""
        return [OrganizationPublisherDocument, UserPublisherDocument]

    def get_index_names(self) -> List[str]:
        """Get the index names for publisher search."""
        from DataSpace import settings

        org_index = settings.ELASTICSEARCH_INDEX_NAMES.get(
            "search.documents.publisher_document.OrganizationPublisherDocument",
            "organization_publisher",
        )
        user_index = settings.ELASTICSEARCH_INDEX_NAMES.get(
            "search.documents.publisher_document.UserPublisherDocument", "user_publisher"
        )
        return [org_index, user_index]

    @trace_method(name="build_query", attributes={"component": "publisher_search"})
    def build_query(self, query: str) -> ESQ:
        """Build the Elasticsearch query for publisher search."""
        if not query:
            return ESQ("match_all")

        # Multi-field search with boosting
        queries = [
            ESQ(
                "multi_match",
                query=query,
                fields=["name^3", "full_name^3"],  # Boost name fields
                fuzziness="AUTO",
            ),
            ESQ(
                "multi_match",
                query=query,
                fields=["description^2", "bio^2"],  # Boost description/bio
                fuzziness="AUTO",
            ),
            ESQ(
                "multi_match",
                query=query,
                fields=["sectors^2"],  # Boost sectors
                fuzziness="AUTO",
            ),
            ESQ(
                "multi_match",
                query=query,
                fields=[
                    "username",
                    "email",
                    "location",
                    "organization_types",
                    "first_name",
                    "last_name",
                ],
                fuzziness="AUTO",
            ),
        ]

        return ESQ("bool", should=queries, minimum_should_match=1)

    @trace_method(name="apply_filters", attributes={"component": "publisher_search"})
    def apply_filters(self, search: Search, filters: Dict[str, str]) -> Search:
        """Apply filters to the search query."""

        if "publisher_type" in filters:
            # Filter by publisher type (organization or user)
            search = search.filter("term", publisher_type=filters["publisher_type"])

        if "sectors" in filters:
            # Filter by sectors
            filter_values = filters["sectors"].split(",")
            search = search.filter("terms", **{"sectors.raw": filter_values})

        if "organization_types" in filters:
            # Filter by organization types
            search = search.filter("term", organization_types=filters["organization_types"])

        if "location" in filters:
            # Filter by location (fuzzy match)
            search = search.filter("match", location=filters["location"])

        return search

    @trace_method(name="build_aggregations", attributes={"component": "publisher_search"})
    def build_aggregations(self, search: Search) -> Search:
        """Build aggregations for faceted search."""

        # Publisher type aggregation
        search.aggs.bucket("publisher_type", "terms", field="publisher_type")

        # Sectors aggregation
        search.aggs.bucket("sectors", "terms", field="sectors.raw", size=50)

        # Organization types aggregation
        search.aggs.bucket("organization_types", "terms", field="organization_types", size=20)

        # Location aggregation (top 20 locations)
        search.aggs.bucket("locations", "terms", field="location.raw", size=20)

        return search

    @trace_method(name="apply_sorting", attributes={"component": "publisher_search"})
    def apply_sorting(self, search: Search, sort_by: str) -> Search:
        """Apply sorting to the search query."""

        if sort_by == "alphabetical":
            search = search.sort("name.raw")
        elif sort_by == "datasets_count":
            search = search.sort({"published_datasets_count": {"order": "desc"}})
        elif sort_by == "usecases_count":
            search = search.sort({"published_usecases_count": {"order": "desc"}})
        elif sort_by == "total_contributions":
            # Sort by total datasets + usecases
            search = search.sort(
                {
                    "_script": {
                        "type": "number",
                        "script": {
                            "source": "doc['published_datasets_count'].value + doc['published_usecases_count'].value"
                        },
                        "order": "desc",
                    }
                }
            )
        elif sort_by == "members_count":
            # Only applicable to organizations
            search = search.sort({"members_count": {"order": "desc"}})
        elif sort_by == "recent":
            search = search.sort({"created": {"order": "desc"}})
        else:
            # Default: relevance score
            pass

        return search

    @trace_method(name="perform_search", attributes={"component": "publisher_search"})
    def perform_search(
        self,
        query: str,
        filters: Dict[str, str],
        page: int,
        size: int,
        sort_by: str = "relevance",
    ) -> Tuple[List[Dict[str, Any]], int, Dict[str, Any]]:
        """Perform the publisher search."""

        # Get index names
        index_names = self.get_index_names()

        if not index_names:
            return [], 0, {}

        # Create multi-index search
        search = Search(index=index_names)

        # Build and apply query
        q = self.build_query(query)
        search = search.query(q)

        # Apply filters
        search = self.apply_filters(search, filters)

        # Apply sorting
        search = self.apply_sorting(search, sort_by)

        # Build aggregations
        search = self.build_aggregations(search)

        # Pagination
        start = (page - 1) * size
        search = search[start : start + size]

        # Execute search
        try:
            response = search.execute()
        except Exception as e:
            self.logger.error("publisher_search_error", error=str(e), exc_info=True)
            return [], 0, {}

        # Process results
        results = []
        for hit in response:
            result = hit.to_dict()
            result["_score"] = hit.meta.score
            result["_index"] = hit.meta.index
            results.append(result)

        # Process aggregations
        aggregations: Dict[str, Any] = {}
        if hasattr(response, "aggregations"):
            aggs_dict = response.aggregations.to_dict()

            for agg_name in ["publisher_type", "sectors", "organization_types", "locations"]:
                if agg_name in aggs_dict:
                    aggregations[agg_name] = {}
                    for bucket in aggs_dict[agg_name]["buckets"]:
                        aggregations[agg_name][bucket["key"]] = bucket["doc_count"]

        total = response.hits.total.value if hasattr(response.hits.total, "value") else len(results)

        return results, total, aggregations

    @trace_method(name="get", attributes={"component": "publisher_search"})
    @track_metrics(name="publisher_search")
    def get(self, request: Any) -> Response:
        """Handle GET request and return search results."""
        try:
            query: str = request.GET.get("query", "")
            page: int = int(request.GET.get("page", 1))
            size: int = int(request.GET.get("size", 10))
            sort_by: str = request.GET.get("sort", "relevance")

            # Handle filters
            filters: Dict[str, str] = {}
            for key, values in request.GET.lists():
                if key not in ["query", "page", "size", "sort"]:
                    if len(values) > 1:
                        filters[key] = ",".join(values)
                    else:
                        filters[key] = values[0]

            # Perform search
            results, total, aggregations = self.perform_search(query, filters, page, size, sort_by)

            # Serialize results
            serializer = self.serializer_class(results, many=True)

            return Response(
                {
                    "results": serializer.data,
                    "total": total,
                    "page": page,
                    "size": size,
                    "aggregations": aggregations,
                }
            )

        except Exception as e:
            self.logger.error("publisher_search_error", error=str(e), exc_info=True)
            return Response({"error": "An internal error has occurred."}, status=500)
