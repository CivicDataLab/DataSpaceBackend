from rest_framework import permissions, status, views
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from authorization.keycloak import keycloak_manager
from authorization.models import User
from authorization.services import AuthorizationService


class KeycloakLoginView(views.APIView):
    """
    View for handling Keycloak login and token exchange.
    Accepts Keycloak tokens and creates Django tokens.
    """

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        # Get the Keycloak token from the request
        keycloak_token = request.data.get("token")
        if not keycloak_token:
            return Response(
                {"error": "Keycloak token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate the token and get user info
        user_info = keycloak_manager.validate_token(keycloak_token)
        if not user_info:
            return Response(
                {"error": "Invalid or expired token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Get user roles from the token
        roles = keycloak_manager.get_user_roles(keycloak_token)

        # Get user organizations from the token
        organizations = keycloak_manager.get_user_organizations(keycloak_token)

        # Sync the user information with our database
        user = keycloak_manager.sync_user_from_keycloak(user_info, roles, organizations)
        if not user:
            return Response(
                {"error": "Failed to synchronize user information"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Create Django tokens for the user
        refresh = RefreshToken.for_user(user)

        # Get user's organizations and their roles
        organizations = AuthorizationService.get_user_organizations(user.id)

        # Get user's dataset-specific permissions
        datasets = AuthorizationService.get_user_datasets(user.id)

        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "is_staff": user.is_staff,
                    "is_superuser": user.is_superuser,
                    "organizations": organizations,
                    "datasets": datasets,
                },
            }
        )


class UserInfoView(views.APIView):
    """
    View for getting the current user's information.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user

        # Get user's organizations and their roles
        organizations = AuthorizationService.get_user_organizations(user.id)  # type: ignore[arg-type]

        # Get user's dataset-specific permissions
        datasets = AuthorizationService.get_user_datasets(user.id)  # type: ignore[arg-type]

        return Response(
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,  # type: ignore[union-attr]
                "first_name": user.first_name,  # type: ignore[union-attr]
                "last_name": user.last_name,  # type: ignore[union-attr]
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "organizations": organizations,
                "datasets": datasets,
            }
        )
