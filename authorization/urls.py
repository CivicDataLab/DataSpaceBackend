from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from authorization.views import KeycloakLoginView, UserInfoView

urlpatterns = [
    # Authentication endpoints
    path("keycloak/login/", KeycloakLoginView.as_view(), name="keycloak_login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("user/info/", UserInfoView.as_view(), name="user_info"),
]
