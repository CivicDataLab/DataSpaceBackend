"""Search view for Event using Elasticsearch.

Only published events are in the index (the document's ``should_index_object``
gate), so this public endpoint never leaks drafts. Filters: location, owner
type (``is_individual_event``) and ``timeframe`` (upcoming / past).
"""

from typing import Any, Dict, List, Optional, Tuple, Union

import structlog
from elasticsearch_dsl import Q as ESQ
from elasticsearch_dsl import Search
from elasticsearch_dsl.query import Query as ESQuery
from rest_framework import serializers
from rest_framework.permissions import AllowAny

from api.models.Event import Event
from api.utils.search_query import nested_paths, text_query
from api.utils.telemetry_utils import trace_method
from api.views.paginated_elastic_view import PaginatedElasticSearchAPIView
from search.documents import EventDocument

logger = structlog.get_logger(__name__)


def timeframe_query(timeframe: str) -> Optional[ESQuery]:
    """Upcoming = not ended yet; past = already ended (dates compared to today, UTC).

    An event's end is its end date, or its start date when it has none. Events
    with no dates at all match neither.
    """
    if timeframe == "upcoming":
        end, start = {"gte": "now/d"}, {"gte": "now/d"}
    elif timeframe == "past":
        end, start = {"lt": "now/d"}, {"lt": "now/d"}
    else:
        return None
    return ESQ(
        "bool",
        should=[
            ESQ("range", end_date=end),
            ESQ(
                "bool",
                must_not=[ESQ("exists", field="end_date")],
                filter=[ESQ("range", start_date=start)],
            ),
        ],
        minimum_should_match=1,
    )


class EventDocumentSerializer(serializers.ModelSerializer):
    """Serializer for the Event search document."""

    public_id = serializers.CharField()
    url_slug = serializers.CharField()
    # Elasticsearch hands dates back as datetimes; show them as plain dates.
    start_date = serializers.DateTimeField(format="%Y-%m-%d", allow_null=True)
    end_date = serializers.DateTimeField(format="%Y-%m-%d", allow_null=True)
    is_individual_event = serializers.BooleanField()
    # Luma cover image (https URL on images.lumacdn.com), null when unknown.
    cover_url = serializers.CharField(default=None, allow_null=True)

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
        model = Event
        fields = [
            "id",
            "name",
            "public_id",
            "url_slug",
            "location",
            "start_date",
            "end_date",
            "status",
            "is_individual_event",
            "cover_url",
            "created",
            "modified",
            "organization",
            "user",
        ]


class SearchEvent(PaginatedElasticSearchAPIView):
    """View for searching events."""

    serializer_class = EventDocumentSerializer
    document_class = EventDocument
    permission_classes = [AllowAny]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.searchable_fields: List[str]
        self.aggregations: Dict[str, str]
        self.searchable_fields, self.aggregations = self.get_searchable_and_aggregations()
        self.logger = structlog.get_logger(__name__)

    @trace_method(
        name="get_searchable_and_aggregations",
        attributes={"component": "search_event"},
    )
    def get_searchable_and_aggregations(self) -> Tuple[List[str], Dict[str, str]]:
        """Searchable fields (name/location/owner) and the facet aggregations."""
        searchable_fields: List[str] = ["name", "location", "organization.name", "user.name"]
        aggregations: Dict[str, str] = {
            "status": "terms",
            "location.raw": "terms",
            "is_individual_event": "terms",
        }
        return searchable_fields, aggregations

    @trace_method(name="add_aggregations", attributes={"component": "search_event"})
    def add_aggregations(self, search: Search) -> Search:
        """Add the facet aggregations to the search query."""
        for aggregation_field in self.aggregations:
            search.aggs.bucket(
                aggregation_field.replace(".raw", ""),
                self.aggregations[aggregation_field],
                field=aggregation_field,
            )
        return search

    @trace_method(name="generate_q_expression", attributes={"component": "search_event"})
    def generate_q_expression(self, query: str) -> Optional[Union[ESQuery, List[ESQuery]]]:
        """Analysed text query over the searchable fields (api/utils/search_query.py)."""
        return text_query(query, self.searchable_fields, nested=nested_paths(self.document_class))

    @trace_method(name="add_filters", attributes={"component": "search_event"})
    def add_filters(self, filters: Dict[str, str], search: Search) -> Search:
        """Apply location / owner-type / timeframe filters."""
        for filter_key in filters:
            if filter_key == "location":
                filter_values = filters[filter_key].split(",")
                search = search.filter("terms", **{"location.raw": filter_values})
            elif filter_key == "is_individual_event":
                value = filters[filter_key].lower() == "true"
                search = search.filter("term", is_individual_event=value)
            elif filter_key == "timeframe":
                timeframe = timeframe_query(filters[filter_key])
                if timeframe is not None:
                    search = search.filter(timeframe)
            elif filter_key == "status":
                search = search.filter("term", **{filter_key: filters[filter_key]})
        return search

    @trace_method(name="add_sort", attributes={"component": "search_event"})
    def add_sort(self, sort: str, search: Search, order: str) -> Search:
        """Apply a sort mode (alphabetical / recent / created / start_date)."""
        if sort == "alphabetical":
            search = search.sort({"name.raw": {"order": order}})
        elif sort == "recent":
            search = search.sort({"modified": {"order": order}})
        elif sort == "created":
            search = search.sort({"created": {"order": order}})
        elif sort == "start_date":
            search = search.sort({"start_date": {"order": order, "missing": "_last"}})
        return search
