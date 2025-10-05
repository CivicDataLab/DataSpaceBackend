import ast
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union, cast

import structlog
from elasticsearch_dsl import A
from elasticsearch_dsl import Q as ESQ
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import Query as ESQuery
from rest_framework import serializers
from rest_framework.permissions import AllowAny

from api.models import Geography, Metadata, UseCase, UseCaseMetadata
from api.utils.telemetry_utils import trace_method, track_metrics
from api.views.paginated_elastic_view import PaginatedElasticSearchAPIView
from search.documents import UseCaseDocument

logger = structlog.get_logger(__name__)


class MetadataSerializer(serializers.Serializer):
    """Serializer for Metadata model."""

    label = serializers.CharField(allow_blank=True)  # type: ignore


class UseCaseMetadataSerializer(serializers.ModelSerializer):
    """Serializer for UseCaseMetadata model."""

    metadata_item = MetadataSerializer()

    class Meta:
        model = UseCaseMetadata
        fields = ["metadata_item", "value"]

    def to_representation(self, instance: UseCaseMetadata) -> Dict[str, Any]:
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


class UseCaseDocumentSerializer(serializers.ModelSerializer):
    """Serializer for UseCase document."""

    metadata = UseCaseMetadataSerializer(many=True)
    tags = serializers.ListField()
    logo = serializers.CharField()
    sectors = serializers.ListField(default=[])
    geographies = serializers.ListField(default=[])
    slug = serializers.CharField()
    is_individual_usecase = serializers.BooleanField()
    running_status = serializers.CharField()
    website = serializers.CharField(required=False, allow_blank=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    platform_url = serializers.CharField(required=False, allow_blank=True)
    started_on = serializers.DateTimeField(required=False, allow_null=True)
    completed_on = serializers.DateTimeField(required=False, allow_null=True)

    class OrganizationSerializer(serializers.Serializer):
        name = serializers.CharField()
        logo = serializers.CharField()

    class UserSerializer(serializers.Serializer):
        name = serializers.CharField()
        bio = serializers.CharField()
        profile_picture = serializers.CharField()

    class ContributorSerializer(serializers.Serializer):
        name = serializers.CharField()
        bio = serializers.CharField()
        profile_picture = serializers.CharField()

    class RelatedOrganizationSerializer(serializers.Serializer):
        name = serializers.CharField()
        logo = serializers.CharField()
        relationship_type = serializers.CharField()

    class DatasetSerializer(serializers.Serializer):
        title = serializers.CharField()
        description = serializers.CharField()
        slug = serializers.CharField()

    organization = OrganizationSerializer()
    user = UserSerializer()
    contributors = ContributorSerializer(many=True)
    organizations = RelatedOrganizationSerializer(many=True)
    datasets = DatasetSerializer(many=True)

    class Meta:
        model = UseCase
        fields = [
            "id",
            "title",
            "summary",
            "slug",
            "created",
            "modified",
            "status",
            "running_status",
            "metadata",
            "tags",
            "logo",
            "sectors",
            "geographies",
            "is_individual_usecase",
            "organization",
            "user",
            "contributors",
            "organizations",
            "datasets",
            "website",
            "contact_email",
            "platform_url",
            "started_on",
            "completed_on",
        ]


class SearchUseCase(PaginatedElasticSearchAPIView):
    """View for searching usecases."""

    serializer_class = UseCaseDocumentSerializer
    document_class = UseCaseDocument
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
        attributes={"component": "search_usecase"},
    )
    def get_searchable_and_aggregations(self) -> Tuple[List[str], Dict[str, str]]:
        """Get searchable fields and aggregations for the search."""
        searchable_fields = [
            "title",
            "summary",
            "tags",
            "sectors",
            "user.name",
            "organization.name",
            "contributors.name",
            "datasets.title",
            "datasets.description",
            "metadata.value",
        ]

        aggregations: Dict[str, str] = {
            "tags.raw": "terms",
            "sectors.raw": "terms",
            "geographies.raw": "terms",
            "status": "terms",
            "running_status": "terms",
        }

        # Add filterable metadata to aggregations
        filterable_metadata = Metadata.objects.filter(filterable=True).all()
        for metadata in filterable_metadata:
            aggregations[f"metadata.{metadata.label}"] = "terms"  # type: ignore

        return searchable_fields, aggregations

    @trace_method(name="add_aggregations", attributes={"component": "search_usecase"})
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
            composite_agg = A(
                "composite",
                sources=[
                    {
                        "metadata_label": {
                            "terms": {"field": "metadata.metadata_item.label"}
                        }
                    },
                    {"metadata_value": {"terms": {"field": "metadata.value"}}},
                ],
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
        name="generate_q_expression", attributes={"component": "search_usecase"}
    )
    def generate_q_expression(
        self, query: str
    ) -> Optional[Union[ESQuery, List[ESQuery]]]:
        """Generate Elasticsearch Query expression."""
        if query:
            queries: List[ESQuery] = []
            for field in self.searchable_fields:
                if field.startswith("datasets."):
                    queries.append(
                        ESQ(
                            "nested",
                            path="datasets",
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
                elif (
                    field.startswith("user.")
                    or field.startswith("organization.")
                    or field.startswith("contributors.")
                    or field.startswith("organizations.")
                ):
                    path = field.split(".")[0]
                    queries.append(
                        ESQ(
                            "nested",
                            path=path,
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

    @trace_method(name="add_filters", attributes={"component": "search_usecase"})
    def add_filters(self, filters: Dict[str, str], search: Search) -> Search:
        """Add filters to the search query."""
        non_filter_metadata = Metadata.objects.filter(filterable=False).all()
        excluded_labels: List[str] = [e.label for e in non_filter_metadata]  # type: ignore

        for filter in filters:
            if filter in excluded_labels:
                continue
            elif filter in ["tags", "sectors", "geographies"]:
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
            elif filter in ["status", "running_status", "is_individual_usecase"]:
                search = search.filter("term", **{filter: filters[filter]})
            elif filter in ["user.name", "organization.name"]:
                path = filter.split(".")[0]
                search = search.filter(
                    "nested",
                    path=path,
                    query={"bool": {"must": {"term": {filter: filters[filter]}}}},
                )
            else:
                # Handle metadata filters
                search = search.filter(
                    "nested",
                    path="metadata",
                    query={
                        "bool": {"must": {"term": {f"metadata.value": filters[filter]}}}
                    },
                )
        return search

    @trace_method(name="add_sort", attributes={"component": "search_usecase"})
    def add_sort(self, sort: str, search: Search, order: str) -> Search:
        """Add sorting to the search query."""
        if sort == "alphabetical":
            search = search.sort({"title.raw": {"order": order}})
        elif sort == "recent":
            search = search.sort({"modified": {"order": order}})
        elif sort == "started":
            search = search.sort({"started_on": {"order": order}})
        elif sort == "completed":
            search = search.sort({"completed_on": {"order": order}})
        return search
