import structlog
from rest_framework import status, views
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from api.utils.keycloak_utils import keycloak_manager
from authorization.consent import UserConsent
from authorization.models import User
from authorization.serializers import UserConsentSerializer
from authorization.services import AuthorizationService

logger = structlog.getLogger(__name__)


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
            logger.warning("Login attempt without token")
            return Response(
                {"error": "Keycloak token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate the token and get user info
        logger.debug(f"Validating token of length: {len(keycloak_token)}")
        user_info = keycloak_manager.validate_token(keycloak_token)
        if not user_info:
            logger.warning("Token validation failed")
            return Response(
                {"error": "Invalid or expired token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Ensure we have a subject ID in the token
        if not user_info.get("sub"):
            logger.warning("Token validation succeeded but missing subject ID")
            return Response(
                {"error": "Token missing required user information"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Get user roles from the token
        roles = keycloak_manager.get_user_roles(keycloak_token)

        # Get user organizations from the token
        organizations = keycloak_manager.get_user_organizations(keycloak_token)

        # Sync the user information with our database
        logger.info(f"Syncing user with Keycloak ID: {user_info.get('sub')}")
        user = keycloak_manager.sync_user_from_keycloak(user_info, roles, organizations)
        if not user:
            logger.error(f"Failed to sync user with Keycloak ID: {user_info.get('sub')}")
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
        import structlog

        logger = structlog.getLogger(__name__)

        user = request.user
        logger.debug(
            f"Getting user info for user: {user.username if hasattr(user, 'username') else 'anonymous'}"
        )

        try:
            # Get user's organizations and their roles
            organizations = AuthorizationService.get_user_organizations(user.id)  # type: ignore[arg-type]

            # Get user's dataset-specific permissions
            datasets = AuthorizationService.get_user_datasets(user.id)  # type: ignore[arg-type]
        except Exception as e:
            logger.error(f"Error retrieving user information: {str(e)}")
            return Response(
                {"error": "Failed to retrieve user information"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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


class UserConsentView(APIView):
    """
    API view for managing user consent for activity tracking.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """
        Get the current user's consent settings.
        """
        try:
            consent = UserConsent.objects.get(user=request.user)  # type: ignore[misc]
        except UserConsent.DoesNotExist:
            # Create a default consent object with tracking disabled
            consent = UserConsent.objects.create(
                user=request.user, activity_tracking_enabled=False  # type: ignore[misc]
            )

        serializer = UserConsentSerializer(consent)
        return Response(serializer.data)

    def put(self, request: Request) -> Response:
        """
        Update the current user's consent settings.
        """
        try:
            consent = UserConsent.objects.get(user=request.user)  # type: ignore[misc]
        except UserConsent.DoesNotExist:
            consent = UserConsent.objects.create(
                user=request.user, activity_tracking_enabled=False  # type: ignore[misc]
            )

        serializer = UserConsentSerializer(consent, data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
