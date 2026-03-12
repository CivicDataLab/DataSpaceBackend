"""
API views for AI model execution.
Handles model inference requests via ModelAPIClient and ModelHFClient.
"""

import logging
from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.models import AIModel
from api.services import ModelAPIClient, ModelHFClient


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def call_aimodel(request: Request, model_id: str) -> Response:
    """
    Execute model inference via appropriate client.

    Args:
        model_id: UUID of the AI model

    Request body:
        {
            "input_text": str,
            "parameters": dict (optional, for API models)
        }

    Returns:
        {
            "success": bool,
            "output": str (if successful),
            "error": str (if failed),
            "latency_ms": float,
            "provider": str,
            ...
        }
    """
    try:
        model = AIModel.objects.get(id=model_id)

        # Check if user has access to this model
        if not model.is_public and model.organization:
            # Check if user belongs to the organization
            if hasattr(request.user, "organizations"):
                user_orgs = request.user.organizations.all()  # type: ignore
            else:
                user_orgs = []
            if model.organization not in user_orgs:
                return Response(
                    {"error": "You do not have access to this model"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        input_text = request.data.get("input_text")
        if not input_text:
            return Response(
                {"error": "input_text is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parameters = request.data.get("parameters", {})
        version_id = request.data.get("version_id")

        # Get the version - either specific version or primary (latest)
        if version_id:
            primary_version = model.versions.filter(id=version_id).first()
            if not primary_version:
                return Response(
                    {"error": f"Version with ID {version_id} not found for this model"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # Fall back to primary (latest) version
            primary_version = model.versions.filter(is_latest=True).first()
            if not primary_version:
                primary_version = model.versions.first()

        if not primary_version:
            return Response(
                {"error": "No version found for this model"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        primary_provider = primary_version.providers.filter(is_primary=True, is_active=True).first()
        if not primary_provider:
            primary_provider = primary_version.providers.filter(is_active=True).first()

        if not primary_provider:
            return Response(
                {"error": "No active provider found for this model"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Route to appropriate client based on provider
        result: Any
        if primary_provider.provider == "HUGGINGFACE":
            hf_client = ModelHFClient(primary_provider)
            result = hf_client.call(input_text)
        else:
            api_client = ModelAPIClient(primary_provider)
            result = api_client.call(input_text, parameters)

        return Response(result, status=status.HTTP_200_OK)

    except AIModel.DoesNotExist:
        return Response(
            {"error": "Model not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except ValueError as e:
        logging.warning(f"ValueError during model execution: {e}")
        return Response(
            {"error": "Invalid input."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logging.exception("Unexpected error during model execution")
        return Response(
            {"error": "Model execution failed."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def call_aimodel_async(request: Request, model_id: str) -> Response:
    """
    Execute model inference asynchronously (for long-running operations).

    This is a placeholder for future async implementation using Celery.
    Currently returns a task_id that can be used to check status.

    Args:
        model_id: UUID of the AI model

    Request body:
        {
            "input_text": str,
            "parameters": dict (optional)
        }

    Returns:
        {
            "task_id": str,
            "status": "pending",
            "model_id": str
        }
    """
    try:
        model = AIModel.objects.get(id=model_id)

        # Check access
        if not model.is_public and model.organization:
            if hasattr(request.user, "organizations"):
                user_orgs = request.user.organizations.all()  # type: ignore
            else:
                user_orgs = []
            if model.organization not in user_orgs:
                return Response(
                    {"error": "You do not have access to this model"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        input_text = request.data.get("input_text")
        if not input_text:
            return Response(
                {"error": "input_text is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # TODO: Implement Celery task for async execution
        # For now, return a placeholder response
        import uuid

        task_id = str(uuid.uuid4())

        return Response(
            {
                "task_id": task_id,
                "status": "pending",
                "model_id": str(model_id),
                "message": "Async execution not yet implemented. Use synchronous endpoint.",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    except AIModel.DoesNotExist:
        return Response(
            {"error": "Model not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
