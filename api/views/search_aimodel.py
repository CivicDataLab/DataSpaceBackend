"""Search view for AIModel using Elasticsearch."""

from typing import Any, Dict, List, Optional, Tuple, Union, cast

import structlog
from elasticsearch_dsl import Q as ESQ
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import Query as ESQuery
from rest_framework import serializers
from rest_framework.permissions import AllowAny

from api.models.AIModel import AIModel
from api.utils.telemetry_utils import trace_method
from api.views.paginated_elastic_view import PaginatedElasticSearchAPIView
from search.documents import AIModelDocument

logger = structlog.get_logger(__name__)


class AIModelDocumentSerializer(serializers.ModelSerializer):
    """Serializer for AIModel document."""

    tags = serializers.ListField()
    supported_languages = serializers.ListField()
    is_individual_model = serializers.BooleanField()
    has_active_endpoints = serializers.BooleanField()
    endpoint_count = serializers.IntegerField()

    class OrganizationSerializer(serializers.Serializer):
        name = serializers.CharField()
        logo = serializers.CharField()

    class UserSerializer(serializers.Serializer):
        name = serializers.CharField()
        bio = serializers.CharField()
        profile_picture = serializers.CharField()

    class EndpointSerializer(serializers.Serializer):
        url = serializers.CharField()
        http_method = serializers.CharField()
        auth_type = serializers.CharField()
        is_primary = serializers.BooleanField()
        is_active = serializers.BooleanField()

    organization = OrganizationSerializer(allow_null=True)
    user = UserSerializer(allow_null=True)
    endpoints = EndpointSerializer(many=True)

    class Meta:
        model = AIModel
        fields = [
            "id",
            "name",
            "display_name",
            "description",
            "version",
            "model_type",
            "provider",
            "provider_model_id",
            "status",
            "is_public",
            "is_active",
            "tags",
            "supported_languages",
            "supports_streaming",
            "max_tokens",
            "average_latency_ms",
            "success_rate",
            "last_audit_score",
            "audit_count",
            "created_at",
            "updated_at",
            "last_tested_at",
            "is_individual_model",
            "has_active_endpoints",
            "endpoint_count",
            "organization",
            "user",
            "endpoints",
        ]


class SearchAIModel(PaginatedElasticSearchAPIView):
    """View for searching AI models."""

    serializer_class = AIModelDocumentSerializer
    document_class = AIModelDocument
    permission_classes = [AllowAny]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.searchable_fields: List[str]
        self.aggregations: Dict[str, str]
        self.searchable_fields, self.aggregations = (
            self.get_searchable_and_aggregations()
        )
        self.logger = structlog.get_logger(__name__)

    @trace_method(
        name="get_searchable_and_aggregations",
        attributes={"component": "search_aimodel"},
    )
    def get_searchable_and_aggregations(self) -> Tuple[List[str], Dict[str, str]]:
        """Get searchable fields and aggregations for the search."""
        searchable_fields: List[str] = [
            "name",
            "display_name",
            "description",
            "tags",
            "provider_model_id",
        ]

        aggregations: Dict[str, str] = {
            "model_type": "terms",
            "provider": "terms",
            "status": "terms",
            "tags.raw": "terms",
            "supported_languages": "terms",
            "is_public": "terms",
            "is_active": "terms",
            "supports_streaming": "terms",
        }

        return searchable_fields, aggregations

    @trace_method(name="add_aggregations", attributes={"component": "search_aimodel"})
    def add_aggregations(self, search: Search) -> Search:
        """Add aggregations to the search query."""
        for aggregation_field in self.aggregations:
            search.aggs.bucket(
                aggregation_field.replace(".raw", ""),
                self.aggregations[aggregation_field],
                field=aggregation_field,
            )
        return search

    @trace_method(
        name="generate_q_expression", attributes={"component": "search_aimodel"}
    )
    def generate_q_expression(
        self, query: str
    ) -> Optional[Union[ESQuery, List[ESQuery]]]:
        """Generate Elasticsearch Query expression."""
        if query:
            queries: List[ESQuery] = []
            for field in self.searchable_fields:
                queries.append(
                    ESQ("fuzzy", **{field: {"value": query, "fuzziness": "AUTO"}})
                )
        else:
            queries = [ESQ("match_all")]

        return ESQ("bool", should=queries, minimum_should_match=1)

    @trace_method(name="add_filters", attributes={"component": "search_aimodel"})
    def add_filters(self, filters: Dict[str, str], search: Search) -> Search:
        """Add filters to the search query."""
        for filter_key in filters:
            if filter_key in ["tags"]:
                # Handle multi-value filters
                raw_filter = filter_key + ".raw"
                if raw_filter in self.aggregations:
                    filter_values = filters[filter_key].split(",")
                    search = search.filter("terms", **{raw_filter: filter_values})
                else:
                    search = search.filter("term", **{filter_key: filters[filter_key]})
            elif filter_key in [
                "model_type",
                "provider",
                "status",
                "supported_languages",
            ]:
                # Handle single or multi-value filters
                filter_values = filters[filter_key].split(",")
                if len(filter_values) > 1:
                    search = search.filter("terms", **{filter_key: filter_values})
                else:
                    search = search.filter("term", **{filter_key: filters[filter_key]})
            elif filter_key in ["is_public", "is_active", "supports_streaming"]:
                # Handle boolean filters
                bool_value = filters[filter_key].lower() in ["true", "1", "yes"]
                search = search.filter("term", **{filter_key: bool_value})
            elif filter_key == "organization":
                # Filter by organization name
                search = search.filter(
                    "nested",
                    path="organization",
                    query={"term": {"organization.name": filters[filter_key]}},
                )
            elif filter_key == "user":
                # Filter by user name
                search = search.filter(
                    "nested",
                    path="user",
                    query={"term": {"user.name": filters[filter_key]}},
                )

        return search

    @trace_method(name="add_sort", attributes={"component": "search_aimodel"})
    def add_sort(self, sort: str, search: Search, order: str) -> Search:
        """Add sorting to the search query."""
        if sort == "alphabetical":
            search = search.sort({"name.raw": {"order": order}})
        elif sort == "recent":
            search = search.sort({"updated_at": {"order": order}})
        elif sort == "created":
            search = search.sort({"created_at": {"order": order}})
        elif sort == "performance":
            # Sort by success_rate, then by average_latency_ms (lower is better)
            search = search.sort(
                {"success_rate": {"order": "desc"}},
                {"average_latency_ms": {"order": "asc"}},
            )
        elif sort == "audit_score":
            search = search.sort({"last_audit_score": {"order": order}})
        elif sort == "popular":
            # Sort by audit_count as a proxy for usage
            search = search.sort({"audit_count": {"order": order}})

        return search
