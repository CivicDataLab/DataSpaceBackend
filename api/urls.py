from django.urls import path
from strawberry.django.views import AsyncGraphQLView

from api.schema import schema
from api.views import index

urlpatterns = [
    path("hello", index.index, name="index"),
    path("graphql", AsyncGraphQLView.as_view(schema=schema, graphql_ide="apollo-sandbox")),
]
