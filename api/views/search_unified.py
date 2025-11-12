"""Unified search view that searches across datasets, usecases, and aimodels."""

from typing import Any, Dict, List, Optional, Tuple, Union

import structlog
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Q as ESQ
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Dataset, Geography, Metadata, UseCase
from api.models.AIModel import AIModel
from api.utils.telemetry_utils import trace_method
from DataSpace import settings
from search.documents import AIModelDocument, DatasetDocument, UseCaseDocument

logger = structlog.get_logger(__name__)


class UnifiedSearchResultSerializer(serializers.Serializer):
    """Serializer for unified search results."""

    id = serializers.CharField()
    type = serializers.CharField()  # 'dataset', 'usecase', or 'aimodel'
    title = serializers.CharField()
    description = serializers.CharField()
    slug = serializers.CharField(required=False)
    created = serializers.DateTimeField(required=False)
    modified = serializers.DateTimeField(required=False)
    created_at = serializers.DateTimeField(required=False)
    updated_at = serializers.DateTimeField(required=False)
    status = serializers.CharField()
    tags = serializers.ListField()
    sectors = serializers.ListField(required=False)
    geographies = serializers.ListField(required=False)

    # Organization and user info
    class OrganizationSerializer(serializers.Serializer):
        name = serializers.CharField()
        logo = serializers.CharField()

    class UserSerializer(serializers.Serializer):
        name = serializers.CharField()
        bio = serializers.CharField(required=False)
        profile_picture = serializers.CharField(required=False)

    organization = OrganizationSerializer(allow_null=True, required=False)
    user = UserSerializer(allow_null=True, required=False)

    # Type-specific fields
    # Dataset specific
    formats = serializers.ListField(required=False)
    has_charts = serializers.BooleanField(required=False)
    download_count = serializers.IntegerField(required=False)
    is_individual_dataset = serializers.BooleanField(required=False)

    # UseCase specific
    running_status = serializers.CharField(required=False)
    logo = serializers.CharField(required=False)
    is_individual_usecase = serializers.BooleanField(required=False)

    # AIModel specific
    name = serializers.CharField(required=False)
    display_name = serializers.CharField(required=False)
    model_type = serializers.CharField(required=False)
    provider = serializers.CharField(required=False)
    is_individual_model = serializers.BooleanField(required=False)


class UnifiedSearch(APIView):
    """View for unified search across datasets, usecases, and aimodels."""

    permission_classes = [AllowAny]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.logger = structlog.get_logger(__name__)

    def _get_index_names(self, types_list: List[str]) -> List[str]:
        """Get Elasticsearch index names for the requested entity types."""
        index_names = []

        if "dataset" in types_list:
            dataset_index = settings.ELASTICSEARCH_INDEX_NAMES.get(
                "search.documents.dataset_document", "dataset"
            )
            index_names.append(dataset_index)

        if "usecase" in types_list:
            usecase_index = settings.ELASTICSEARCH_INDEX_NAMES.get(
                "search.documents.usecase_document", "usecase"
            )
            index_names.append(usecase_index)

        if "aimodel" in types_list:
            aimodel_index = settings.ELASTICSEARCH_INDEX_NAMES.get(
                "search.documents.aimodel_document", "aimodel"
            )
            index_names.append(aimodel_index)

        return index_names

    def _build_unified_query(self, query: str) -> ESQ:
        """Build a unified query that works across all document types."""
        if not query:
            return ESQ("match_all")

        # Common fields across all types
        common_queries = [
            ESQ(
                "multi_match",
                query=query,
                fields=["title^3", "name^3", "display_name^3"],
                fuzziness="AUTO",
            ),
            ESQ(
                "multi_match",
                query=query,
                fields=["description^2", "summary^2"],
                fuzziness="AUTO",
            ),
            ESQ("multi_match", query=query, fields=["tags^2"], fuzziness="AUTO"),
        ]

        # Type-specific nested queries
        # Dataset resources
        common_queries.append(
            ESQ(
                "nested",
                path="resources",
                query=ESQ(
                    "bool",
                    should=[
                        ESQ("wildcard", **{"resources.name": {"value": f"*{query}*"}}),
                        ESQ(
                            "wildcard",
                            **{"resources.description": {"value": f"*{query}*"}},
                        ),
                    ],
                ),
                ignore_unmapped=True,  # Important: ignore if index doesn't have this field
            )
        )

        # UseCase nested fields
        common_queries.extend(
            [
                ESQ(
                    "nested",
                    path="datasets",
                    query=ESQ(
                        "multi_match",
                        query=query,
                        fields=["datasets.title", "datasets.description"],
                        fuzziness="AUTO",
                    ),
                    ignore_unmapped=True,
                ),
                ESQ(
                    "nested",
                    path="contributors",
                    query=ESQ(
                        "match",
                        **{"contributors.name": {"query": query, "fuzziness": "AUTO"}},
                    ),
                    ignore_unmapped=True,
                ),
            ]
        )

        # Organization and user (common across types)
        common_queries.extend(
            [
                ESQ(
                    "nested",
                    path="organization",
                    query=ESQ(
                        "match",
                        **{"organization.name": {"query": query, "fuzziness": "AUTO"}},
                    ),
                    ignore_unmapped=True,
                ),
                ESQ(
                    "nested",
                    path="user",
                    query=ESQ(
                        "match", **{"user.name": {"query": query, "fuzziness": "AUTO"}}
                    ),
                    ignore_unmapped=True,
                ),
            ]
        )

        return ESQ("bool", should=common_queries, minimum_should_match=1)

    def _apply_filters(self, search: Search, filters: Dict[str, str]) -> Search:
        """Apply filters to the search query."""
        if "tags" in filters:
            filter_values = filters["tags"].split(",")
            search = search.filter("terms", **{"tags.raw": filter_values})

        if "sectors" in filters:
            filter_values = filters["sectors"].split(",")
            search = search.filter("terms", **{"sectors.raw": filter_values})

        if "geographies" in filters:
            filter_values = filters["geographies"].split(",")
            filter_values = Geography.get_geography_names_with_descendants(
                filter_values
            )
            search = search.filter("terms", **{"geographies.raw": filter_values})

        if "status" in filters:
            search = search.filter("term", status=filters["status"])

        return search

    def _normalize_result(self, hit: Any) -> Dict[str, Any]:
        """Normalize a search hit to a common format."""
        result = hit.to_dict()
        result["_score"] = hit.meta.score
        result["_index"] = hit.meta.index

        # Determine type from index name
        index_name = hit.meta.index.lower()
        if "dataset" in index_name:
            result["type"] = "dataset"
        elif "usecase" in index_name:
            result["type"] = "usecase"
        elif "aimodel" in index_name:
            result["type"] = "aimodel"
        else:
            result["type"] = "unknown"

        # Normalize field names based on type
        if result["type"] == "usecase":
            if "summary" in result:
                result["description"] = result.get("summary", "")
            if "title" not in result:
                result["title"] = ""
        elif result["type"] == "aimodel":
            if "display_name" in result:
                result["title"] = result.get("display_name", "")
            elif "name" in result:
                result["title"] = result.get("name", "")
            else:
                result["title"] = ""
            if "description" not in result:
                result["description"] = ""
            # AIModel uses created_at/updated_at
            if "created_at" in result:
                result["created"] = result["created_at"]
            if "updated_at" in result:
                result["modified"] = result["updated_at"]
        else:  # dataset
            if "title" not in result:
                result["title"] = ""
            if "description" not in result:
                result["description"] = ""

        return result  # type: ignore[no-any-return]

    @trace_method(name="unified_search", attributes={"component": "unified_search"})
    def perform_unified_search(
        self,
        query: str,
        filters: Dict[str, str],
        types_list: List[str],
        page: int,
        size: int,
    ) -> Tuple[List[Dict[str, Any]], int, Dict[str, Any]]:
        """Perform unified search across multiple indices."""
        # Get index names
        index_names = self._get_index_names(types_list)

        if not index_names:
            return [], 0, {}

        # Create multi-index search
        search = Search(index=index_names)

        # Build and apply query
        q = self._build_unified_query(query)
        search = search.query(q)

        # Apply filters
        search = self._apply_filters(search, filters)

        # Add aggregations
        search.aggs.bucket("types", "terms", field="_index")
        search.aggs.bucket("tags", "terms", field="tags.raw", size=50)
        search.aggs.bucket("sectors", "terms", field="sectors.raw", size=50)
        search.aggs.bucket("geographies", "terms", field="geographies.raw", size=50)
        search.aggs.bucket("status", "terms", field="status")

        # Pagination
        start = (page - 1) * size
        search = search[start : start + size]

        # Execute search
        response = search.execute()

        # Normalize results
        results = [self._normalize_result(hit) for hit in response]

        # Process aggregations
        aggregations: Dict[str, Any] = {}
        if hasattr(response, "aggregations"):
            aggs_dict = response.aggregations.to_dict()

            # Process types aggregation
            if "types" in aggs_dict:
                aggregations["types"] = {}
                for bucket in aggs_dict["types"]["buckets"]:
                    index_name = bucket["key"]
                    if "dataset" in index_name:
                        aggregations["types"]["dataset"] = bucket["doc_count"]
                    elif "usecase" in index_name:
                        aggregations["types"]["usecase"] = bucket["doc_count"]
                    elif "aimodel" in index_name:
                        aggregations["types"]["aimodel"] = bucket["doc_count"]

            # Process other aggregations
            for agg_name in ["tags", "sectors", "geographies", "status"]:
                if agg_name in aggs_dict:
                    aggregations[agg_name] = {}
                    for bucket in aggs_dict[agg_name]["buckets"]:
                        aggregations[agg_name][bucket["key"]] = bucket["doc_count"]

        total = (
            response.hits.total.value
            if hasattr(response.hits.total, "value")
            else len(results)
        )

        return results, total, aggregations

    @trace_method(name="get", attributes={"component": "unified_search"})
    def get(self, request: Any) -> Response:
        """Handle GET request and return unified search results."""
        try:
            query: str = request.GET.get("query", "")
            page: int = int(request.GET.get("page", 1))
            size: int = int(request.GET.get("size", 10))
            entity_types: str = request.GET.get(
                "types", "dataset,usecase,aimodel"
            )  # Which entity types to search

            # Parse entity types
            types_list = [t.strip() for t in entity_types.split(",")]

            # Handle filters
            filters: Dict[str, str] = {}
            for key, values in request.GET.lists():
                if key not in ["query", "page", "size", "types"]:
                    if len(values) > 1:
                        filters[key] = ",".join(values)
                    else:
                        filters[key] = values[0]

            # Perform unified search
            results, total, aggregations = self.perform_unified_search(
                query, filters, types_list, page, size
            )

            # Serialize results
            serializer = UnifiedSearchResultSerializer(results, many=True)

            result = {
                "results": serializer.data,
                "total": total,
                "aggregations": aggregations,
                "types_searched": types_list,
            }

            return Response(result)

        except Exception as e:
            self.logger.error("unified_search_error", error=str(e), exc_info=True)
            return Response({"error": "An internal error has occurred."}, status=500)

    def _build_aggregations(
        self, results: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, int]]:
        """Build aggregations from results."""
        aggregations: Dict[str, Dict[str, int]] = {
            "types": {},
            "tags": {},
            "sectors": {},
            "geographies": {},
            "status": {},
        }

        for result in results:
            # Count by type
            result_type = result.get("type", "unknown")
            aggregations["types"][result_type] = (
                aggregations["types"].get(result_type, 0) + 1
            )

            # Count by tags
            for tag in result.get("tags", []):
                aggregations["tags"][tag] = aggregations["tags"].get(tag, 0) + 1

            # Count by sectors
            for sector in result.get("sectors", []):
                aggregations["sectors"][sector] = (
                    aggregations["sectors"].get(sector, 0) + 1
                )

            # Count by geographies
            for geography in result.get("geographies", []):
                aggregations["geographies"][geography] = (
                    aggregations["geographies"].get(geography, 0) + 1
                )

            # Count by status
            status = result.get("status", "unknown")
            aggregations["status"][status] = aggregations["status"].get(status, 0) + 1

        return aggregations
