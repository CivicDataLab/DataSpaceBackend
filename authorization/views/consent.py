from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authorization.consent import UserConsent
from authorization.serializers import UserConsentSerializer


class UserConsentView(APIView):
    """
    API view for managing user consent for activity tracking.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get the current user's consent settings.
        """
        try:
            consent = UserConsent.objects.get(user=request.user)
        except UserConsent.DoesNotExist:
            # Create a default consent object with tracking disabled
            consent = UserConsent.objects.create(
                user=request.user, activity_tracking_enabled=False
            )

        serializer = UserConsentSerializer(consent)
        return Response(serializer.data)

    def put(self, request):
        """
        Update the current user's consent settings.
        """
        try:
            consent = UserConsent.objects.get(user=request.user)
        except UserConsent.DoesNotExist:
            consent = UserConsent.objects.create(
                user=request.user, activity_tracking_enabled=False
            )

        serializer = UserConsentSerializer(
            consent, data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
