"""GraphQL types for AI Model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional, cast

import strawberry
import strawberry_django
import structlog
from strawberry.enum import EnumType
from strawberry.types import Info

from api.models.AIModel import AIModel, ModelEndpoint
from api.models.AIModelVersion import AIModelVersion, VersionProvider
from api.types.base_type import BaseType
from api.types.type_dataset import TypeTag
from api.types.type_geo import TypeGeo
from api.types.type_organization import TypeOrganization
from api.types.type_sector import TypeSector
from api.utils.enums import (
    AIModelFramework,
    AIModelLifecycleStage,
    AIModelProvider,
    AIModelStatus,
    AIModelType,
    EndpointAuthType,
    EndpointHTTPMethod,
    HFModelClass,
)
from authorization.types import TypeUser

logger = structlog.get_logger("dataspace.type_aimodel")


# Create GraphQL enums from Django TextChoices
AIModelTypeEnum = strawberry.enum(AIModelType)  # type: ignore
AIModelStatusEnum = strawberry.enum(AIModelStatus)  # type: ignore
AIModelProviderEnum = strawberry.enum(AIModelProvider)  # type: ignore
EndpointAuthTypeEnum = strawberry.enum(EndpointAuthType)  # type: ignore
EndpointHTTPMethodEnum = strawberry.enum(EndpointHTTPMethod)  # type: ignore
AIModelFrameworkEnum = strawberry.enum(AIModelFramework)  # type: ignore
HFModelClassEnum = strawberry.enum(HFModelClass)  # type: ignore
AIModelLifecycleStageEnum = strawberry.enum(AIModelLifecycleStage)  # type: ignore


@strawberry.type
class TypeModelEndpoint(BaseType):
    """GraphQL type for ModelEndpoint."""

    id: int
    url: str
    http_method: EndpointHTTPMethodEnum
    auth_type: EndpointAuthTypeEnum
    auth_header_name: str
    headers: strawberry.scalars.JSON
    request_template: strawberry.scalars.JSON
    response_path: Optional[str]
    timeout_seconds: int
    max_retries: int
    is_primary: bool
    is_active: bool
    rate_limit_per_minute: Optional[int]
    last_success_at: Optional[datetime]
    last_failure_at: Optional[datetime]
    total_requests: int
    failed_requests: int
    created_at: datetime
    updated_at: datetime

    @strawberry.field
    def success_rate(self) -> Optional[float]:
        """Calculate success rate."""
        if self.total_requests == 0:
            return None
        return ((self.total_requests - self.failed_requests) / self.total_requests) * 100


@strawberry_django.filter(AIModel)
class AIModelFilter:
    """Filter for AI Model."""

    id: Optional[int]
    status: Optional[AIModelStatusEnum]
    model_type: Optional[AIModelTypeEnum]
    provider: Optional[AIModelProviderEnum]
    is_public: Optional[bool]
    is_active: Optional[bool]


@strawberry_django.order(AIModel)
class AIModelOrder:
    """Order for AI Model."""

    name: strawberry.auto
    display_name: strawberry.auto
    created_at: strawberry.auto
    updated_at: strawberry.auto
    last_tested_at: strawberry.auto


@strawberry_django.type(
    AIModel,
    fields="__all__",
    filters=AIModelFilter,
    pagination=True,
    order=AIModelOrder,  # type: ignore
)
class TypeAIModel(BaseType):
    """GraphQL type for AI Model."""

    id: int
    name: str
    display_name: str
    version: Optional[str]
    description: str
    model_type: AIModelTypeEnum
    provider: AIModelProviderEnum
    provider_model_id: Optional[str]
    organization: Optional["TypeOrganization"]
    user: Optional["TypeUser"]
    supports_streaming: bool
    max_tokens: Optional[int]
    supported_languages: strawberry.scalars.JSON
    input_schema: strawberry.scalars.JSON
    output_schema: strawberry.scalars.JSON
    metadata: strawberry.scalars.JSON
    status: AIModelStatusEnum
    is_public: bool
    is_active: bool
    average_latency_ms: Optional[float]
    success_rate: Optional[float]
    last_audit_score: Optional[float]
    audit_count: int
    created_at: datetime
    updated_at: datetime
    last_tested_at: Optional[datetime]

    @strawberry.field
    def endpoints(self, info: Info) -> List[TypeModelEndpoint]:
        """Get endpoints for this AI model.

        Args:
            info: Request info

        Returns:
            List[TypeModelEndpoint]: List of endpoints
        """
        try:
            django_instance = cast(AIModel, self)
            queryset = django_instance.endpoints.all()
            return TypeModelEndpoint.from_django_list(list(queryset))
        except (AttributeError, AIModel.DoesNotExist):
            return []

    @strawberry.field(description="Get tags associated with this AI model.")
    def tags(self) -> Optional[List[TypeTag]]:
        """Get tags associated with this AI model."""
        try:
            queryset = self.tags.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeTag.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get sectors associated with this AI model.")
    def sectors(self) -> Optional[List[TypeSector]]:
        """Get sectors associated with this AI model."""
        try:
            queryset = self.sectors.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeSector.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get geographies associated with this AI model.")
    def geographies(self) -> Optional[List[TypeGeo]]:
        """Get geographies associated with this AI model."""
        try:
            queryset = self.geographies.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeGeo.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get primary endpoint for this model.")
    def primary_endpoint(self) -> Optional[TypeModelEndpoint]:
        """Get primary endpoint for this model."""
        endpoint = self.get_primary_endpoint()  # type: ignore
        if endpoint:
            return TypeModelEndpoint.from_django(endpoint)
        return None

    @strawberry.field(description="Get all versions of this AI model.")
    def versions(self) -> List["TypeAIModelVersion"]:
        """Get all versions of this AI model."""
        try:
            django_instance = cast(AIModel, self)
            queryset = django_instance.versions.all()
            return TypeAIModelVersion.from_django_list(list(queryset))
        except Exception:
            return []

    @strawberry.field(description="Get the latest version of this AI model.")
    def latest_version(self) -> Optional["TypeAIModelVersion"]:
        """Get the latest version of this AI model."""
        try:
            django_instance = cast(AIModel, self)
            version = django_instance.versions.filter(is_latest=True).first()
            if not version:
                version = django_instance.versions.order_by("-created_at").first()
            if version:
                return TypeAIModelVersion.from_django(version)
            return None
        except Exception:
            return None


@strawberry.type
class TypeVersionProvider(BaseType):
    """GraphQL type for VersionProvider."""

    id: int
    provider: AIModelProviderEnum
    provider_model_id: Optional[str]
    is_primary: bool
    is_active: bool
    hf_use_pipeline: bool
    hf_auth_token: Optional[str]
    hf_model_class: Optional[str]
    hf_attn_implementation: Optional[str]
    framework: Optional[str]
    config: strawberry.scalars.JSON
    created_at: datetime
    updated_at: datetime


@strawberry_django.filter(AIModelVersion)
class AIModelVersionFilter:
    """Filter for AI Model Version."""

    id: Optional[int]
    status: Optional[AIModelStatusEnum]
    is_latest: Optional[bool]


@strawberry_django.order(AIModelVersion)
class AIModelVersionOrder:
    """Order for AI Model Version."""

    version: strawberry.auto
    created_at: strawberry.auto
    updated_at: strawberry.auto


@strawberry.type
class TypeAIModelVersion(BaseType):
    """GraphQL type for AI Model Version."""

    id: int
    version: str
    version_notes: Optional[str]
    supports_streaming: bool
    max_tokens: Optional[int]
    supported_languages: strawberry.scalars.JSON
    input_schema: strawberry.scalars.JSON
    output_schema: strawberry.scalars.JSON
    metadata: strawberry.scalars.JSON
    status: AIModelStatusEnum
    lifecycle_stage: AIModelLifecycleStageEnum
    is_latest: bool
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime]

    @strawberry.field
    def providers(self) -> List[TypeVersionProvider]:
        """Get all providers for this version."""
        try:
            django_instance = cast(AIModelVersion, self)
            queryset = django_instance.providers.all()
            return TypeVersionProvider.from_django_list(list(queryset))
        except Exception:
            return []

    @strawberry.field
    def primary_provider(self) -> Optional[TypeVersionProvider]:
        """Get the primary provider for this version."""
        try:
            django_instance = cast(AIModelVersion, self)
            provider = django_instance.providers.filter(is_primary=True).first()
            if provider:
                return TypeVersionProvider.from_django(provider)
            return None
        except Exception:
            return None

    @strawberry.field
    def ai_model(self) -> Optional[TypeAIModel]:
        """Get the parent AI model."""
        try:
            django_instance = cast(AIModelVersion, self)
            return TypeAIModel.from_django(django_instance.ai_model)
        except Exception:
            return None
