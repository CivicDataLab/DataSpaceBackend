import abc
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from elasticsearch_dsl import Search
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.views import APIView

from api.models import Metadata

T = TypeVar("T")
SearchType = TypeVar("SearchType", bound=Search)
SerializerType = TypeVar("SerializerType", bound=Serializer)


class PaginatedElasticSearchAPIView(Generic[SerializerType, SearchType], APIView):
    """Base class for paginated Elasticsearch API views."""

    serializer_class: Type[SerializerType]
    document_class: Type[SearchType]
    permission_classes = [AllowAny]  # Allow unauthenticated access by default

    @abc.abstractmethod
    def generate_q_expression(self, query: str) -> Any:
        """This method should be overridden and return a Q() expression."""
        pass

    @abc.abstractmethod
    def add_aggregations(self, search: SearchType) -> SearchType:
        """This method should be overridden and return a Search object with aggregations added."""
        pass

    @abc.abstractmethod
    def add_filters(self, filters: Dict[str, Any], search: SearchType) -> SearchType:
        """This method should be overridden and return a Search object with filters added."""
        pass

    @abc.abstractmethod
    def add_sort(self, sort: str, search: SearchType) -> SearchType:
        """This method should be overridden and return a Search object with sort added."""
        pass

    def get_search(self) -> SearchType:
        """Get search instance."""
        if hasattr(self.document_class, "search"):
            return self.document_class.search()  # type: ignore
        raise AttributeError(
            f"{self.document_class.__name__} does not have a search method"
        )

    def get(self, request: HttpRequest) -> Response:
        """Handle GET request and return paginated search results."""
        try:
            # Generate cache key based on request parameters
            cache_key = self._generate_cache_key(request)
            cached_result: Optional[Dict[str, Any]] = cache.get(cache_key)

            if cached_result:
                return Response(cached_result)

            # Original search logic
            query: str = request.GET.get("query", "")
            page: int = int(request.GET.get("page", 1))
            size: int = int(request.GET.get("size", 10))
            sort: str = request.GET.get("sort", "alphabetical")
            filters: Dict[str, Any] = request.GET.dict()
            filters.pop("query", None)
            filters.pop("page", None)
            filters.pop("size", None)
            filters.pop("sort", None)

            q = self.generate_q_expression(query)
            search = self.get_search().query(q)
            search = self.add_aggregations(search)
            search = self.add_filters(filters, search)
            search = self.add_sort(sort, search)
            search = search[(page - 1) * size : page * size]
            response = search.execute()

            serializer = self.serializer_class(response, many=True)
            aggregations: Dict[str, Any] = response.aggregations.to_dict()

            metadata_aggregations = aggregations["metadata"]["filtered_metadata"][
                "composite_agg"
            ]["buckets"]
            aggregations.pop("metadata")
            for agg in metadata_aggregations:
                label: str = agg["key"]["metadata_label"]
                value: str = agg["key"]["metadata_value"]
                if label not in aggregations:
                    aggregations[label] = {}
                aggregations[label][value] = agg["doc_count"]

            categories_agg = aggregations["categories"]["buckets"]
            aggregations.pop("categories")
            aggregations["categories"] = {}
            for agg in categories_agg:
                aggregations["categories"][agg["key"]] = agg["doc_count"]

            tags_agg = aggregations["tags"]["buckets"]
            aggregations.pop("tags")
            aggregations["tags"] = {}
            for agg in tags_agg:
                aggregations["tags"][agg["key"]] = agg["doc_count"]

            formats_agg = aggregations["formats"]["buckets"]
            aggregations.pop("formats")
            aggregations["formats"] = {}
            for agg in formats_agg:
                aggregations["formats"][agg["key"]] = agg["doc_count"]

            result: Dict[str, Any] = {
                "results": serializer.data,
                "total": response.hits.total.value,  # type: ignore
                "aggregations": aggregations,
            }

            # Cache the result
            cache.set(cache_key, result, timeout=3600)  # Cache for 1 hour

            return Response(result)
        except Exception as e:
            return Response(str(e), status=500)

    def _generate_cache_key(self, request: HttpRequest) -> str:
        """Generate a unique cache key based on request parameters."""
        params: Dict[str, str] = {
            "query": request.GET.get("query", ""),
            "page": request.GET.get("page", "1"),
            "size": request.GET.get("size", "10"),
            "sort": request.GET.get("sort", "alphabetical"),
            "filters": str(sorted(request.GET.dict().items())),
        }
        return f"search_results:{hash(frozenset(params.items()))}"
