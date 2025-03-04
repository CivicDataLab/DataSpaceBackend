import abc
from django.core.cache import cache
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Metadata


class PaginatedElasticSearchAPIView(APIView):
    serializer_class = None
    document_class = None

    @abc.abstractmethod
    def generate_q_expression(self, query):
        """This method should be overridden
        and return a Q() expression."""

    @abc.abstractmethod
    def add_aggregations(self, search):
        """This method should be overridden
        and return a Search object with aggregations added."""

    @abc.abstractmethod
    def add_filters(self, filters, search):
        """This method should be overridden
        and return a Search object with filters added."""

    @abc.abstractmethod
    def add_sort(self, sort, search):
        """This method should be overridden
        and return a Search object with filters added."""

    def get(self, request):
        try:
            # Generate cache key based on request parameters
            cache_key = self._generate_cache_key(request)
            cached_result = cache.get(cache_key)
            
            if cached_result:
                return Response(cached_result)

            # Original search logic
            query = request.GET.get('query', '')
            page = int(request.GET.get('page', 1))
            size = int(request.GET.get('size', 10))
            sort = request.GET.get('sort', 'alphabetical')
            filters = request.GET.dict()
            filters.pop('query', None)
            filters.pop("page", None)
            filters.pop("size", None)
            filters.pop("sort", None)
            
            q = self.generate_q_expression(query)
            search = self.document_class.search().query(q)
            search = self.add_aggregations(search)
            search = self.add_filters(filters, search)
            search = self.add_sort(sort, search)
            search = search[(page - 1) * size:page * size]
            response = search.execute()


            serializer = self.serializer_class(response, many=True)
            aggregations = response.aggregations.to_dict()

            metadata_aggregations = aggregations['metadata']['filtered_metadata']['composite_agg']['buckets']
            aggregations.pop('metadata')
            for agg in metadata_aggregations:
                label = agg["key"]["metadata_label"]
                value = agg["key"]["metadata_value"]
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

            result = {
                'results': serializer.data,
                'total': response.hits.total.value,
                'aggregations': aggregations
            }

            # Cache the result
            cache.set(cache_key, result, timeout=3600)  # Cache for 1 hour

            return Response(result)
        except Exception as e:
            return HttpResponse(e, status=500)

    def _generate_cache_key(self, request):
        """Generate a unique cache key based on request parameters"""
        params = {
            'query': request.GET.get('query', ''),
            'page': request.GET.get('page', '1'),
            'size': request.GET.get('size', '10'),
            'sort': request.GET.get('sort', 'alphabetical'),
            'filters': str(sorted(request.GET.dict().items()))
        }
        return f"search_results:{hash(frozenset(params.items()))}"
