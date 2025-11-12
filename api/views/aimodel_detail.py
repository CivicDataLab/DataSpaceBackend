"""API view for AI Model detail."""

from typing import Any, Dict, List, Optional

import logging
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models.AIModel import AIModel, ModelEndpoint


logger = logging.getLogger(__name__)

class ModelEndpointSerializer(serializers.ModelSerializer):
    """Serializer for Model Endpoint."""

    class Meta:
        model = ModelEndpoint
        fields = [
            "id",
            "url",
            "http_method",
            "auth_type",
            "timeout_seconds",
            "is_primary",
            "is_active",
        ]


class AIModelDetailSerializer(serializers.ModelSerializer):
    """Serializer for AI Model detail."""

    tags = serializers.SerializerMethodField()
    sectors = serializers.SerializerMethodField()
    geographies = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    endpoints = ModelEndpointSerializer(many=True, read_only=True)

    class Meta:
        model = AIModel
        fields = [
            "id",
            "name",
            "display_name",
            "version",
            "description",
            "model_type",
            "provider",
            "provider_model_id",
            "supports_streaming",
            "max_tokens",
            "supported_languages",
            "input_schema",
            "output_schema",
            "tags",
            "sectors",
            "geographies",
            "metadata",
            "status",
            "is_public",
            "is_active",
            "average_latency_ms",
            "success_rate",
            "last_audit_score",
            "audit_count",
            "created_at",
            "updated_at",
            "last_tested_at",
            "organization",
            "user",
            "endpoints",
        ]

    def get_tags(self, obj: Any) -> List[str]:
        """Get tags."""
        return [tag.value for tag in obj.tags.all()]

    def get_sectors(self, obj: Any) -> List[str]:
        """Get sectors."""
        return [sector.name for sector in obj.sectors.all()]

    def get_geographies(self, obj: Any) -> List[str]:
        """Get geographies."""
        return [geography.name for geography in obj.geographies.all()]

    def get_organization(self, obj: Any) -> Optional[Dict[str, Any]]:
        """Get organization."""
        if obj.organization:
            return {
                "id": str(obj.organization.id),
                "name": obj.organization.name,
                "logo": obj.organization.logo.url if obj.organization.logo else None,
            }
        return None

    def get_user(self, obj: Any) -> Optional[Dict[str, Any]]:
        """Get user."""
        if obj.user:
            return {
                "id": str(obj.user.id),
                "name": obj.user.get_full_name() or obj.user.username,
                "profile_picture": (
                    obj.user.profile_picture.url if obj.user.profile_picture else None
                ),
            }
        return None


class AIModelDetailView(APIView):
    """API view for AI Model detail."""

    permission_classes = [AllowAny]

    def get(self, request: Request, model_id: str) -> Response:
        """Get AI model details."""
        try:
            model = AIModel.objects.prefetch_related(
                "tags", "sectors", "geographies", "endpoints", "organization", "user"
            ).get(id=model_id)

            serializer = AIModelDetailSerializer(model)
            return Response(serializer.data)

        except AIModel.DoesNotExist:
            return Response({"error": "AI Model not found"}, status=404)
        except Exception as e:
            logger.exception("Unexpected exception in AIModelDetailView.get")
            return Response({"error": "An internal error has occurred."}, status=500)
