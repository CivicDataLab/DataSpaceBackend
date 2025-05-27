# mypy: disable-error-code=no-untyped-def
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.activities.display import (
    format_activity_stream_for_display,
    get_combined_activity_stream,
    get_object_activity_stream,
    get_organization_activity_stream,
    get_target_activity_stream,
    get_user_activity_stream,
)
from api.models.Dataset import Dataset
from api.models.Organization import Organization
from api.models.Resource import Resource
from api.models.UseCase import UseCase


class UserActivityView(APIView):
    """
    API view for retrieving a user's activity stream.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get the current user's activity stream.
        """
        limit = int(request.query_params.get("limit", 20))
        activities = get_user_activity_stream(request.user, request, limit=limit)
        formatted_activities = format_activity_stream_for_display(activities)
        return Response(formatted_activities)


class DatasetActivityView(APIView):
    """
    API view for retrieving a dataset's activity stream.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, dataset_id):
        """
        Get the activity stream for a specific dataset.
        """
        try:
            dataset = Dataset.objects.get(id=dataset_id)
            limit = int(request.query_params.get("limit", 20))
            activities = get_object_activity_stream(dataset, request, limit=limit)
            formatted_activities = format_activity_stream_for_display(activities)
            return Response(formatted_activities)
        except Dataset.DoesNotExist:
            return Response(
                {"error": "Dataset not found"}, status=status.HTTP_404_NOT_FOUND
            )


class OrganizationActivityView(APIView):
    """
    API view for retrieving an organization's activity stream.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, organization_id):
        """
        Get the activity stream for a specific organization.
        """
        try:
            limit = int(request.query_params.get("limit", 20))
            activities = get_organization_activity_stream(
                organization_id, request, limit=limit
            )
            formatted_activities = format_activity_stream_for_display(activities)
            return Response(formatted_activities)
        except Organization.DoesNotExist:
            return Response(
                {"error": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )


class ResourceActivityView(APIView):
    """
    API view for retrieving a resource's activity stream.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, resource_id):
        """
        Get the activity stream for a specific resource.
        """
        try:
            resource = Resource.objects.get(id=resource_id)
            limit = int(request.query_params.get("limit", 20))
            activities = get_object_activity_stream(resource, request, limit=limit)
            formatted_activities = format_activity_stream_for_display(activities)
            return Response(formatted_activities)
        except Resource.DoesNotExist:
            return Response(
                {"error": "Resource not found"}, status=status.HTTP_404_NOT_FOUND
            )


class UseCaseActivityView(APIView):
    """
    API view for retrieving a use case's activity stream.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, usecase_id):
        """
        Get the activity stream for a specific use case.
        """
        try:
            usecase = UseCase.objects.get(id=usecase_id)
            limit = int(request.query_params.get("limit", 20))
            activities = get_object_activity_stream(usecase, request, limit=limit)
            formatted_activities = format_activity_stream_for_display(activities)
            return Response(formatted_activities)
        except UseCase.DoesNotExist:
            return Response(
                {"error": "Use case not found"}, status=status.HTTP_404_NOT_FOUND
            )


class GlobalActivityView(APIView):
    """
    API view for retrieving the global activity stream.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get the global activity stream.
        """
        limit = int(request.query_params.get("limit", 20))
        activities = get_combined_activity_stream(request, limit=limit)
        formatted_activities = format_activity_stream_for_display(activities)
        return Response(formatted_activities)
