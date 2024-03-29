from django.urls import path
from strawberry.django.views import AsyncGraphQLView, GraphQLView

from api.schema.schema import schema
from api.views import index

urlpatterns = [
    path("hello", index.index, name="index"),
    path("graphql", GraphQLView.as_view(schema=schema, graphql_ide="apollo-sandbox")),
]
