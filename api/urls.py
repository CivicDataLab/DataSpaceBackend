from django.urls import path
from api.views import index
from strawberry.django.views import GraphQLView
from api.schema import schema



urlpatterns = [
    path("hello", index.index, name="index"),
    path("graphql", GraphQLView.as_view(schema=schema)),
] 