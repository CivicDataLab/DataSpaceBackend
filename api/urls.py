from django.urls import path
from strawberry.django.views import AsyncGraphQLView, GraphQLView

from api.schema.schema import schema
from api.views import index, search_dataset

urlpatterns = [
    path("hello", index.index, name="index"),
    # path("search/dataset/<str:query>/", search_dataset.SearchDataset.as_view(), name="search_dataset"),
    path("graphql", GraphQLView.as_view(schema=schema, graphql_ide="apollo-sandbox")),
]
