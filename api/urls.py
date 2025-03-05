from django.conf import settings
from django.urls import include, path, re_path
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers
from strawberry.django.views import AsyncGraphQLView, GraphQLView

from api.schema.schema import schema
from api.views import download, generate_dynamic_chart, search_dataset

urlpatterns = [
    # API endpoints
    path(
        "search/dataset/", search_dataset.SearchDataset.as_view(), name="search_dataset"
    ),
    path(
        "graphql",
        csrf_exempt(
            GraphQLView.as_view(
                schema=schema,
                graphql_ide="apollo-sandbox",
            )
        ),
    ),
    re_path(
        r"download/(?P<type>resource|access_resource|chart|chart_image)/(?P<id>[0-9a-f]{8}\-[0-9a-f]{4}\-4[0-9a-f]{3}\-[89ab][0-9a-f]{3}\-[0-9a-f]{12})",
        download,
    ),
    re_path(
        r"generate-dynamic-chart/(?P<resource_id>[0-9a-f]{8}\-[0-9a-f]{4}\-4[0-9a-f]{3}\-[89ab][0-9a-f]{3}\-[0-9a-f]{12})",
        generate_dynamic_chart,
        name="generate_dynamic_chart",
    ),
]
