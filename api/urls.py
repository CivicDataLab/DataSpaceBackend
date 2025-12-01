from django.conf import settings
from django.urls import include, path, re_path
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers
from rest_framework_simplejwt.views import TokenRefreshView
from strawberry.django.views import AsyncGraphQLView, GraphQLView

from api.schema.schema import schema
from api.views import (
    aimodel_detail,
    aimodel_execution,
    auth,
    download,
    generate_dynamic_chart,
    search_aimodel,
    search_dataset,
    search_unified,
    search_usecase,
    trending_datasets,
)
from api.views.activity import (
    DatasetActivityView,
    GlobalActivityView,
    OrganizationActivityView,
    ResourceActivityView,
    UseCaseActivityView,
    UserActivityView,
)

urlpatterns = [
    # Authentication endpoints
    path("auth/keycloak/login/", auth.KeycloakLoginView.as_view(), name="keycloak_login"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/user/info/", auth.UserInfoView.as_view(), name="user_info"),
    # API endpoints
    path("search/dataset/", search_dataset.SearchDataset.as_view(), name="search_dataset"),
    path("search/usecase/", search_usecase.SearchUseCase.as_view(), name="search_usecase"),
    path("search/aimodel/", search_aimodel.SearchAIModel.as_view(), name="search_aimodel"),
    path("search/unified/", search_unified.UnifiedSearch.as_view(), name="search_unified"),
    path(
        "aimodels/<model_id>/",
        aimodel_detail.AIModelDetailView.as_view(),
        name="aimodel_detail",
    ),
    path(
        "aimodels/<model_id>/call/",
        aimodel_execution.call_aimodel,
        name="aimodel_call",
    ),
    path(
        "aimodels/<model_id>/call-async/",
        aimodel_execution.call_aimodel_async,
        name="aimodel_call_async",
    ),
    path(
        "trending/datasets/",
        trending_datasets.TrendingDatasets.as_view(),
        name="trending_datasets",
    ),
    # Single, simple GraphQL endpoint with no redirects
    path(
        "graphql",
        csrf_exempt(
            GraphQLView.as_view(
                schema=schema,
                graphql_ide=None,  # Disable IDE to simplify response
                get_context=lambda request, *args, **kwargs: request,
            )
        ),
    ),
    re_path(  # type: ignore
        r"download/(?P<type>resource|access_resource|chart|chart_image)/(?P<id>[0-9a-f]{8}\-[0-9a-f]{4}\-4[0-9a-f]{3}\-[89ab][0-9a-f]{3}\-[0-9a-f]{12})",
        download,
    ),
    re_path(  # type: ignore
        r"generate-dynamic-chart/(?P<resource_id>[0-9a-f]{8}\-[0-9a-f]{4}\-4[0-9a-f]{3}\-[89ab][0-9a-f]{3}\-[0-9a-f]{12})",
        generate_dynamic_chart,
        name="generate_dynamic_chart",
    ),
    # Activity Stream endpoints
    path("activities/user/", UserActivityView.as_view(), name="user_activities"),
    path("activities/global/", GlobalActivityView.as_view(), name="global_activities"),
    path(
        "activities/dataset/<uuid:dataset_id>/",
        DatasetActivityView.as_view(),
        name="dataset_activities",
    ),
    path(
        "activities/organization/<str:organization_id>/",
        OrganizationActivityView.as_view(),
        name="organization_activities",
    ),
    path(
        "activities/resource/<uuid:resource_id>/",
        ResourceActivityView.as_view(),
        name="resource_activities",
    ),
    path(
        "activities/usecase/<int:usecase_id>/",
        UseCaseActivityView.as_view(),
        name="usecase_activities",
    ),
]
