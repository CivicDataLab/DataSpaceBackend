import abc

from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView


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
        and return a Q() expression."""

    def get(self, request):
        try:
            query = request.GET.get('query', '')
            page = int(request.GET.get('page', 1))
            size = int(request.GET.get('size', 10))
            q = self.generate_q_expression(query)
            search = self.document_class.search().query(q)
            search = self.add_aggregations(search)
            search = search[(page - 1) * size:page * size]
            response = search.execute()

            print(f'Found {response.hits.total.value} hit(s) for query: "{query}"')

            serializer = self.serializer_class(response, many=True)
            return Response({'results': serializer.data, 'aggregations': response.aggregations.to_dict()})
        except Exception as e:
            return HttpResponse(e, status=500)
