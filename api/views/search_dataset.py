import ast
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union, cast

import structlog
from elasticsearch_dsl import A
from elasticsearch_dsl import Q as ESQ
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import Query as ESQuery
from rest_framework import serializers
from rest_framework.permissions import AllowAny

from api.models import Dataset, DatasetMetadata, Geography, Metadata
from api.utils.telemetry_utils import trace_method, track_metrics
from api.views.paginated_elastic_view import PaginatedElasticSearchAPIView
from search.documents import DatasetDocument

logger = structlog.get_logger(__name__)


class MetadataSerializer(serializers.Serializer):
    """Serializer for Metadata model."""

    label = serializers.CharField(allow_blank=True)  # type: ignore


class DatasetMetadataSerializer(serializers.ModelSerializer):
    """Serializer for DatasetMetadata model."""

    metadata_item = MetadataSerializer()

    class Meta:
        model = DatasetMetadata
        fields = ["metadata_item", "value"]

    def to_representation(self, instance: DatasetMetadata) -> Dict[str, Any]:
        representation = super().to_representation(instance)

        if isinstance(representation["value"], str):
            try:
                value_list = ast.literal_eval(representation["value"])
                if isinstance(value_list, list):
                    representation["value"] = ", ".join(str(x) for x in value_list)
            except (ValueError, SyntaxError):
                pass

        return cast(Dict[str, Any], representation)

    def to_internal_value(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(data.get("value"), str):
            try:
                value = data["value"]
                data["value"] = value.split(", ") if value else []
            except (ValueError, SyntaxError):
                pass

        return cast(Dict[str, Any], super().to_internal_value(data))


class DatasetDocumentSerializer(serializers.ModelSerializer):
    """Serializer for Dataset document."""

    metadata = DatasetMetadataSerializer(many=True)
    tags = serializers.ListField()
    sectors = serializers.ListField()
    formats = serializers.ListField()
    catalogs = serializers.ListField()
    geographies = serializers.ListField()
    has_charts = serializers.BooleanField()
    slug = serializers.CharField()
    download_count = serializers.IntegerField()
    trending_score = serializers.FloatField(required=False)
    is_individual_dataset = serializers.BooleanField()

    class OrganizationSerializer(serializers.Serializer):
        name = serializers.CharField()
        logo = serializers.CharField()

    class UserSerializer(serializers.Serializer):
        name = serializers.CharField()
        bio = serializers.CharField()
        profile_picture = serializers.CharField()

    organization = OrganizationSerializer()
    user = UserSerializer()

    class Meta:
        model = Dataset
        fields = [
            "id",
            "title",
            "description",
            "slug",
            "created",
            "modified",
            "status",
            "metadata",
            "tags",
            "sectors",
            "formats",
            "catalogs",
            "geographies",
            "has_charts",
            "download_count",
            "trending_score",
            "is_individual_dataset",
            "organization",
            "user",
        ]


class SearchDataset(PaginatedElasticSearchAPIView):
    """View for searching datasets."""

    serializer_class = DatasetDocumentSerializer
    document_class = DatasetDocument
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
        attributes={"component": "search_dataset"},
    )
    def get_searchable_and_aggregations(self) -> Tuple[List[str], Dict[str, str]]:
        """Get searchable fields and aggregations for the search."""
        enabled_metadata = Metadata.objects.filter(enabled=True).all()
        searchable_fields: List[str] = []
        searchable_fields.extend(
            [
                "tags",
                "description",
                "resources.description",
                "resources.name",
                "title",
                "metadata.value",
            ]
        )
        aggregations: Dict[str, str] = {
            "tags.raw": "terms",
            "sectors.raw": "terms",
            "formats.raw": "terms",
            "catalogs.raw": "terms",
            "geographies.raw": "terms",
        }
        for metadata in enabled_metadata:  # type: Metadata
            if metadata.filterable:
                aggregations[f"metadata.{metadata.label}"] = "terms"
        return searchable_fields, aggregations

    @trace_method(name="add_aggregations", attributes={"component": "search_dataset"})
    def add_aggregations(self, search: Search) -> Search:
        """Add aggregations to the search query for metadata value and label using composite aggregation."""
        aggregate_fields: List[str] = []
        for aggregation_field in self.aggregations:
            if aggregation_field.startswith("metadata."):
                field_name = aggregation_field.split(".")[1]
                aggregate_fields.append(field_name)
            else:
                search.aggs.bucket(
                    aggregation_field.replace(".raw", ""),
                    self.aggregations[aggregation_field],
                    field=aggregation_field,
                )

        if aggregate_fields:
            metadata_qs = Metadata.objects.filter(filterable=True)
            filterable_metadata = [str(meta.label) for meta in metadata_qs]  # type: ignore

            metadata_bucket = search.aggs.bucket("metadata", "nested", path="metadata")
            composite_sources = [
                {
                    "metadata_label": {
                        "terms": {"field": "metadata.metadata_item.label"}
                    }
                },
                {"metadata_value": {"terms": {"field": "metadata.value"}}},
            ]
            composite_agg = A(
                "composite",
                sources=composite_sources,  # type: ignore[arg-type]
                size=10000,
            )
            metadata_filter = A(
                "filter",
                {  # type: ignore[arg-type]
                    "bool": {
                        "must": [
                            {
                                "terms": {
                                    "metadata.metadata_item.label": filterable_metadata
                                }
                            }
                        ]
                    }
                },
            )
            metadata_bucket.bucket("filtered_metadata", metadata_filter).bucket(
                "composite_agg", composite_agg
            )

        return search

    @trace_method(
        name="generate_q_expression", attributes={"component": "search_dataset"}
    )
    def generate_q_expression(
        self, query: str
    ) -> Optional[Union[ESQuery, List[ESQuery]]]:
        """Generate Elasticsearch Query expression."""
        if query:
            queries: List[ESQuery] = []
            for field in self.searchable_fields:
                if field.startswith("resources.name") or field.startswith(
                    "resources.description"
                ):
                    queries.append(
                        ESQ(
                            "nested",
                            path="resources",
                            query=ESQ(
                                "bool",
                                should=[
                                    ESQ("wildcard", **{field: {"value": f"*{query}*"}}),
                                    ESQ(
                                        "fuzzy",
                                        **{
                                            field: {"value": query, "fuzziness": "AUTO"}
                                        },
                                    ),
                                ],
                            ),
                        )
                    )
                else:
                    queries.append(
                        ESQ("fuzzy", **{field: {"value": query, "fuzziness": "AUTO"}})
                    )
        else:
            queries = [ESQ("match_all")]

        return ESQ("bool", should=queries, minimum_should_match=1)

    @trace_method(name="add_filters", attributes={"component": "search_dataset"})
    def add_filters(self, filters: Dict[str, str], search: Search) -> Search:
        """Add filters to the search query."""
        non_filter_metadata = Metadata.objects.filter(filterable=False).all()
        excluded_labels: List[str] = [e.label for e in non_filter_metadata]  # type: ignore

        for filter in filters:
            if filter in excluded_labels:
                continue
            elif filter in ["tags", "sectors", "formats", "catalogs", "geographies"]:
                raw_filter = filter + ".raw"
                if raw_filter in self.aggregations:
                    filter_values = filters[filter].split(",")

                    # For geographies, expand to include all descendant geographies
                    if filter == "geographies":
                        filter_values = Geography.get_geography_names_with_descendants(
                            filter_values
                        )

                    search = search.filter("terms", **{raw_filter: filter_values})
                else:
                    search = search.filter("term", **{filter: filters[filter]})
            else:
                search = search.filter(
                    "nested",
                    path="metadata",
                    query={
                        "bool": {"must": {"term": {f"metadata.value": filters[filter]}}}
                    },
                )
        return search

    @trace_method(name="add_sort", attributes={"component": "search_dataset"})
    def add_sort(self, sort: str, search: Search, order: str) -> Search:
        """Add sorting to the search query."""
        if sort == "alphabetical":
            search = search.sort({"title.raw": {"order": order}})
        elif sort == "recent":
            search = search.sort({"modified": {"order": order}})
        elif sort == "trending":
            search = search.sort({"trending_score": {"order": order}})
        elif sort == "popular":
            search = search.sort({"download_count": {"order": order}})
        return search
