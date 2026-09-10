"""Search view for Publication (UI "Resource") using Elasticsearch.

Only published resources are in the index (the document's ``should_index_object``
gate), so this public endpoint never leaks drafts. Filters: resource type,
sector, geography.
"""

from typing import Any, Dict, List, Optional, Tuple, Union

import structlog
from elasticsearch_dsl import Q as ESQ
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import Query as ESQuery
from rest_framework import serializers
from rest_framework.permissions import AllowAny

from api.models.Publication import Publication
from api.utils.telemetry_utils import trace_method
from api.views.paginated_elastic_view import PaginatedElasticSearchAPIView
from search.documents import PublicationDocument

logger = structlog.get_logger(__name__)


class PublicationDocumentSerializer(serializers.ModelSerializer):
    """Serializer for the Publication search document."""

    resource_type = serializers.CharField(allow_blank=True)
    sectors = serializers.ListField()
    geographies = serializers.ListField()

    class OrganizationSerializer(serializers.Serializer):
        name = serializers.CharField()
        logo = serializers.CharField()

    class UserSerializer(serializers.Serializer):
        name = serializers.CharField()
        bio = serializers.CharField()
        profile_picture = serializers.CharField()

    organization = OrganizationSerializer(allow_null=True)
    user = UserSerializer(allow_null=True)

    class Meta:
        model = Publication
        fields = [
            "id",
            "title",
            "description",
            "status",
            "resource_type",
            "sectors",
            "geographies",
            "created",
            "modified",
            "organization",
            "user",
        ]


class SearchPublication(PaginatedElasticSearchAPIView):
    """View for searching resources."""

    serializer_class = PublicationDocumentSerializer
    document_class = PublicationDocument
    permission_classes = [AllowAny]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.searchable_fields: List[str]
        self.aggregations: Dict[str, str]
        self.searchable_fields, self.aggregations = self.get_searchable_and_aggregations()
        self.logger = structlog.get_logger(__name__)

    @trace_method(
        name="get_searchable_and_aggregations",
        attributes={"component": "search_publication"},
    )
    def get_searchable_and_aggregations(self) -> Tuple[List[str], Dict[str, str]]:
        """Searchable fields (name/description) and the three facet aggregations."""
        searchable_fields: List[str] = ["title", "description"]
        aggregations: Dict[str, str] = {
            "status": "terms",
            "resource_type.raw": "terms",
            "sectors.raw": "terms",
            "geographies.raw": "terms",
        }
        return searchable_fields, aggregations

    @trace_method(name="add_aggregations", attributes={"component": "search_publication"})
    def add_aggregations(self, search: Search) -> Search:
        """Add the facet aggregations to the search query."""
        for aggregation_field in self.aggregations:
            search.aggs.bucket(
                aggregation_field.replace(".raw", ""),
                self.aggregations[aggregation_field],
                field=aggregation_field,
            )
        return search

    @trace_method(name="generate_q_expression", attributes={"component": "search_publication"})
    def generate_q_expression(self, query: str) -> Optional[Union[ESQuery, List[ESQuery]]]:
        """Build a fuzzy query over the searchable fields, or match-all when blank."""
        if query:
            queries: List[ESQuery] = [
                ESQ("fuzzy", **{field: {"value": query, "fuzziness": "AUTO"}})
                for field in self.searchable_fields
            ]
        else:
            queries = [ESQ("match_all")]
        return ESQ("bool", should=queries, minimum_should_match=1)

    @trace_method(name="add_filters", attributes={"component": "search_publication"})
    def add_filters(self, filters: Dict[str, str], search: Search) -> Search:
        """Apply resource-type / sector / geography facet filters."""
        for filter_key in filters:
            if filter_key in ["resource_type", "sectors", "geographies"]:
                raw_filter = filter_key + ".raw"
                filter_values = filters[filter_key].split(",")
                search = search.filter("terms", **{raw_filter: filter_values})
            elif filter_key == "status":
                search = search.filter("term", **{filter_key: filters[filter_key]})
        return search

    @trace_method(name="add_sort", attributes={"component": "search_publication"})
    def add_sort(self, sort: str, search: Search, order: str) -> Search:
        """Apply a sort mode (alphabetical / recent / created)."""
        if sort == "alphabetical":
            search = search.sort({"title.raw": {"order": order}})
        elif sort == "recent":
            search = search.sort({"modified": {"order": order}})
        elif sort == "created":
            search = search.sort({"created": {"order": order}})
        return search
