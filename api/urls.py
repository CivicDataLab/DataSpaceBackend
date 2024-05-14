from django.urls import path, re_path
from strawberry.django.views import AsyncGraphQLView, GraphQLView

from api.schema.schema import schema
from api.views import search_dataset, download

urlpatterns = [
    # path("hello", index.index, name="index"),
    # path("search/dataset/<str:query>/", search_dataset.SearchDataset.as_view(), name="search_dataset"),
    path("graphql", GraphQLView.as_view(schema=schema, graphql_ide="apollo-sandbox")),
    re_path(
        r"download/(?P<type>resource|access_resource)/(?P<id>[0-9a-f]{8}\-[0-9a-f]{4}\-4[0-9a-f]{3}\-[89ab][0-9a-f]{3}\-[0-9a-f]{12})",
        download)
]
