"""GraphQL schema for AI Model."""

# mypy: disable-error-code=union-attr

import datetime
from typing import List, Optional

import strawberry
import strawberry_django
from django.core.exceptions import ValidationError as DjangoValidationError
from strawberry.types import Info
from strawberry_django.pagination import OffsetPaginationInput

from api.models.AIModel import AIModel, ModelAPIKey, ModelEndpoint
from api.models.AIModelVersion import AIModelVersion, VersionProvider
from api.models.Dataset import Tag
from api.schema.base_mutation import BaseMutation, MutationResponse
from api.schema.extensions import TrackActivity, TrackModelActivity
from api.types.type_aimodel import (
    AIModelFilter,
    AIModelLifecycleStageEnum,
    AIModelOrder,
    AIModelProviderEnum,
    AIModelStatusEnum,
    AIModelTypeEnum,
    AIModelVersionFilter,
    AIModelVersionOrder,
    EndpointAuthTypeEnum,
    EndpointHTTPMethodEnum,
    TypeAIModel,
    TypeAIModelVersion,
    TypeModelEndpoint,
    TypeVersionProvider,
)
from api.utils.graphql_telemetry import trace_resolver
from authorization.graphql_permissions import IsAuthenticated
from authorization.models import OrganizationMembership, Role


@trace_resolver(name="update_aimodel_tags", attributes={"component": "aimodel"})
def _update_aimodel_tags(model: AIModel, tags: Optional[List[str]]) -> None:
    """Update tags for an AI model."""
    if tags is None:
        return
    model.tags.clear()
    for tag in tags:
        model.tags.add(Tag.objects.get_or_create(defaults={"value": tag}, value__iexact=tag)[0])
    model.save()


def _update_aimodel_sectors(model: AIModel, sectors: List[str]) -> None:
    """Helper function to update sectors for an AI model."""
    from api.models import Sector

    model.sectors.clear()
    for sector_name in sectors:
        try:
            sector = Sector.objects.get(name__iexact=sector_name)
            model.sectors.add(sector)
        except Sector.DoesNotExist:
            pass
    model.save()


def _update_aimodel_geographies(model: AIModel, geographies: List[int]) -> None:
    """Helper function to update geographies for an AI model."""
    from api.models import Geography

    model.geographies.clear()
    for geography_id in geographies:
        try:
            geography = Geography.objects.get(id=geography_id)
            model.geographies.add(geography)
        except Geography.DoesNotExist:
            pass
    model.save()


@strawberry.input
class CreateAIModelInput:
    """Input for creating a new AI Model."""

    model_type: AIModelTypeEnum
    provider: AIModelProviderEnum
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    provider_model_id: Optional[str] = None
    supports_streaming: bool = False
    max_tokens: Optional[int] = None
    supported_languages: Optional[List[str]] = None
    input_schema: Optional[strawberry.scalars.JSON] = None
    output_schema: Optional[strawberry.scalars.JSON] = None
    tags: Optional[List[str]] = None
    sectors: Optional[List[str]] = None
    geographies: Optional[List[int]] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    is_public: bool = False


@strawberry.input
class UpdateAIModelInput:
    """Input for updating an AI Model."""

    id: int
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    model_type: Optional[AIModelTypeEnum] = None
    provider: Optional[AIModelProviderEnum] = None
    version: Optional[str] = None
    provider_model_id: Optional[str] = None
    supports_streaming: Optional[bool] = None
    max_tokens: Optional[int] = None
    supported_languages: Optional[List[str]] = None
    input_schema: Optional[strawberry.scalars.JSON] = None
    output_schema: Optional[strawberry.scalars.JSON] = None
    tags: Optional[List[str]] = None
    sectors: Optional[List[str]] = None
    geographies: Optional[List[int]] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    is_public: Optional[bool] = None
    is_active: Optional[bool] = None
    status: Optional[AIModelStatusEnum] = None


@strawberry.input
class CreateModelEndpointInput:
    """Input for creating a model endpoint."""

    model_id: int
    url: str
    http_method: EndpointHTTPMethodEnum = EndpointHTTPMethodEnum.POST
    auth_type: EndpointAuthTypeEnum = EndpointAuthTypeEnum.BEARER
    auth_header_name: str = "Authorization"
    headers: Optional[strawberry.scalars.JSON] = None
    request_template: Optional[strawberry.scalars.JSON] = None
    response_path: Optional[str] = None
    timeout_seconds: int = 30
    max_retries: int = 3
    is_primary: bool = True
    is_active: bool = True
    rate_limit_per_minute: Optional[int] = None


@strawberry.input
class UpdateModelEndpointInput:
    """Input for updating a model endpoint."""

    id: int
    url: Optional[str] = None
    http_method: Optional[EndpointHTTPMethodEnum] = None
    auth_type: Optional[EndpointAuthTypeEnum] = None
    auth_header_name: Optional[str] = None
    headers: Optional[strawberry.scalars.JSON] = None
    request_template: Optional[strawberry.scalars.JSON] = None
    response_path: Optional[str] = None
    timeout_seconds: Optional[int] = None
    max_retries: Optional[int] = None
    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None
    rate_limit_per_minute: Optional[int] = None


@strawberry.input
class CreateAIModelVersionInput:
    """Input for creating a new AI Model Version."""

    model_id: int
    version: str
    version_notes: Optional[str] = ""
    lifecycle_stage: Optional[AIModelLifecycleStageEnum] = None
    supports_streaming: bool = False
    max_tokens: Optional[int] = None
    supported_languages: Optional[List[str]] = None
    input_schema: Optional[strawberry.scalars.JSON] = None
    output_schema: Optional[strawberry.scalars.JSON] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    copy_from_version_id: Optional[int] = None
    is_latest: Optional[bool] = None


@strawberry.input
class UpdateAIModelVersionInput:
    """Input for updating an AI Model Version."""

    id: int
    version: Optional[str] = None
    version_notes: Optional[str] = None
    lifecycle_stage: Optional[AIModelLifecycleStageEnum] = None
    supports_streaming: Optional[bool] = None
    max_tokens: Optional[int] = None
    supported_languages: Optional[List[str]] = None
    input_schema: Optional[strawberry.scalars.JSON] = None
    output_schema: Optional[strawberry.scalars.JSON] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    status: Optional[AIModelStatusEnum] = None
    is_latest: Optional[bool] = None


@strawberry.input
class CreateVersionProviderInput:
    """Input for creating a new Version Provider."""

    version_id: int
    provider: AIModelProviderEnum
    provider_model_id: Optional[str] = ""
    is_primary: bool = False
    is_active: bool = True
    hf_use_pipeline: bool = False
    hf_auth_token: Optional[str] = None
    hf_model_class: Optional[str] = None
    hf_attn_implementation: Optional[str] = "flash_attention_2"
    framework: Optional[str] = None
    config: Optional[strawberry.scalars.JSON] = None


@strawberry.input
class UpdateVersionProviderInput:
    """Input for updating a Version Provider."""

    id: int
    provider_model_id: Optional[str] = None
    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None
    hf_use_pipeline: Optional[bool] = None
    hf_auth_token: Optional[str] = None
    hf_model_class: Optional[str] = None
    hf_attn_implementation: Optional[str] = None
    framework: Optional[str] = None
    config: Optional[strawberry.scalars.JSON] = None


@strawberry.type
class Query:
    """Queries for AI Models."""

    @strawberry_django.field(
        filters=AIModelFilter,
        pagination=True,
        order=AIModelOrder,
    )
    @trace_resolver(name="ai_models", attributes={"component": "aimodel"})
    def ai_models(
        self,
        info: Info,
        filters: Optional[AIModelFilter] = strawberry.UNSET,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[AIModelOrder] = strawberry.UNSET,
    ) -> List[TypeAIModel]:
        """Get all AI models."""
        organization = info.context.context.get("organization")
        user = info.context.user

        if organization:
            queryset = AIModel.objects.filter(organization=organization)
        else:
            # If user is authenticated
            if user.is_authenticated:
                # If user is superuser, show all models
                if user.is_superuser:
                    queryset = AIModel.objects.all()
                else:
                    # For authenticated users, show their models and public models
                    queryset = AIModel.objects.filter(user=user) | AIModel.objects.filter(
                        is_public=True, is_active=True
                    )
            else:
                # For non-authenticated users, only show public active models
                queryset = AIModel.objects.filter(is_public=True, is_active=True)

        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        queryset = queryset.distinct()

        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return TypeAIModel.from_django_list(list(queryset))

    @strawberry.field
    @trace_resolver(name="get_ai_model", attributes={"component": "aimodel"})
    def get_ai_model(self, info: Info, model_id: int) -> Optional[TypeAIModel]:
        """Get an AI model by ID."""
        user = info.context.user
        try:
            model = AIModel.objects.get(id=model_id)

            # Check permissions
            if model.is_public and model.is_active:
                return TypeAIModel.from_django(model)

            if not user.is_authenticated:
                return None

            if user.is_superuser or model.user == user:
                return TypeAIModel.from_django(model)

            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if org_member and org_member.role.can_view:
                    return TypeAIModel.from_django(model)

            return None
        except AIModel.DoesNotExist:
            return None

    @strawberry.field
    @trace_resolver(name="get_model_endpoints", attributes={"component": "aimodel"})
    def get_model_endpoints(self, info: Info, model_id: int) -> List[TypeModelEndpoint]:
        """Get all endpoints for an AI model."""
        user = info.context.user
        try:
            model = AIModel.objects.get(id=model_id)

            # Check permissions
            if not model.is_public and not user.is_authenticated:
                return []

            if not model.is_public and model.user != user and not user.is_superuser:
                if model.organization:
                    org_member = OrganizationMembership.objects.filter(
                        user=user, organization=model.organization
                    ).first()
                    if not org_member or not org_member.role.can_view:
                        return []
                else:
                    return []

            endpoints = ModelEndpoint.objects.filter(model=model)
            return TypeModelEndpoint.from_django_list(list(endpoints))
        except AIModel.DoesNotExist:
            return []


@strawberry.type
class Mutation:
    """Mutations for AI Models."""

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="create_ai_model",
        trace_attributes={"component": "aimodel"},
        track_activity={
            "verb": "created",
            "get_data": lambda result, **kwargs: {
                "model_id": str(result.id),
                "model_name": result.name,
                "organization": (str(result.organization.id) if result.organization else None),
            },
        },
    )
    def create_ai_model(
        self, info: Info, input: CreateAIModelInput
    ) -> MutationResponse[TypeAIModel]:
        """Create a new AI model."""
        organization = info.context.context.get("organization")
        user = info.context.user

        # Generate default values if not provided (similar to dataset creation)
        timestamp = datetime.datetime.now().strftime("%d %b %Y - %H:%M:%S")
        name = input.name or f"untitled-ai-model-{timestamp}"
        display_name = input.display_name or f"Untitled AI Model - {timestamp}"
        description = input.description or ""

        # Prepare supported_languages
        supported_languages = input.supported_languages or []

        # Prepare schemas
        input_schema = input.input_schema or {}
        output_schema = input.output_schema or {}

        # Prepare metadata
        metadata = input.metadata or {}

        try:
            model = AIModel.objects.create(
                name=name,
                display_name=display_name,
                version=input.version or "",
                description=description,
                model_type=input.model_type,
                provider=input.provider,
                provider_model_id=input.provider_model_id or "",
                organization=organization,
                user=user,
                supports_streaming=input.supports_streaming,
                max_tokens=input.max_tokens,
                supported_languages=supported_languages,
                input_schema=input_schema,
                output_schema=output_schema,
                metadata=metadata,
                is_public=input.is_public,
                status="REGISTERED",
            )
            # Handle tags separately after model creation
            if input.tags is not None:
                _update_aimodel_tags(model, input.tags)

            # Handle sectors
            if input.sectors is not None:
                _update_aimodel_sectors(model, input.sectors)

            # Handle geographies
            if input.geographies is not None:
                _update_aimodel_geographies(model, input.geographies)

            return MutationResponse.success_response(TypeAIModel.from_django(model))
        except Exception as e:
            raise DjangoValidationError(f"Failed to create AI model: {str(e)}")

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="update_ai_model",
        trace_attributes={"component": "aimodel"},
        track_activity={
            "verb": "updated",
            "get_data": lambda result, **kwargs: {
                "model_id": str(result.id),
                "model_name": result.name,
                "organization": (str(result.organization.id) if result.organization else None),
            },
        },
    )
    def update_ai_model(
        self, info: Info, input: UpdateAIModelInput
    ) -> MutationResponse[TypeAIModel]:
        """Update an AI model."""
        user = info.context.user

        try:
            model = AIModel.objects.get(id=input.id)
        except AIModel.DoesNotExist:
            raise DjangoValidationError(f"AI Model with ID {input.id} does not exist.")

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_change:
                    raise DjangoValidationError("You don't have permission to update this model.")
            else:
                raise DjangoValidationError("You don't have permission to update this model.")

        # Update fields
        if input.name is not None:
            model.name = input.name
        if input.display_name is not None:
            model.display_name = input.display_name
        if input.description is not None:
            model.description = input.description
        if input.version is not None:
            model.version = input.version
        if input.provider_model_id is not None:
            model.provider_model_id = input.provider_model_id
        if input.supports_streaming is not None:
            model.supports_streaming = input.supports_streaming
        if input.max_tokens is not None:
            model.max_tokens = input.max_tokens
        if input.supported_languages is not None:
            model.supported_languages = input.supported_languages
        if input.input_schema is not None:
            model.input_schema = input.input_schema
        if input.output_schema is not None:
            model.output_schema = input.output_schema
        if input.metadata is not None:
            model.metadata = input.metadata
        if input.is_public is not None:
            model.is_public = input.is_public
        if input.is_active is not None:
            model.is_active = input.is_active
        if input.status is not None:
            model.status = input.status
        if input.model_type is not None:
            model.model_type = input.model_type
        if input.provider is not None:
            model.provider = input.provider

        model.save()

        # Handle tags separately
        if input.tags is not None:
            _update_aimodel_tags(model, input.tags)

        # Handle sectors
        if input.sectors is not None:
            _update_aimodel_sectors(model, input.sectors)

        # Handle geographies
        if input.geographies is not None:
            _update_aimodel_geographies(model, input.geographies)

        return MutationResponse.success_response(TypeAIModel.from_django(model))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="delete_ai_model",
        trace_attributes={"component": "aimodel"},
        track_activity={
            "verb": "deleted",
            "get_data": lambda result, **kwargs: {
                "model_id": str(kwargs.get("model_id")),
                "success": result,
            },
        },
    )
    def delete_ai_model(self, info: Info, model_id: int) -> MutationResponse[bool]:
        """Delete an AI model."""
        user = info.context.user

        try:
            model = AIModel.objects.get(id=model_id)
        except AIModel.DoesNotExist:
            raise DjangoValidationError(f"AI Model with ID {model_id} does not exist.")

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_delete:
                    raise DjangoValidationError("You don't have permission to delete this model.")
            else:
                raise DjangoValidationError("You don't have permission to delete this model.")

        model.delete()
        return MutationResponse.success_response(True)

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="create_model_endpoint",
        trace_attributes={"component": "aimodel"},
        track_activity={
            "verb": "created endpoint",
            "get_data": lambda result, **kwargs: {
                "endpoint_id": str(result.id),
                "model_id": str(result.model.id),
            },
        },
    )
    def create_model_endpoint(
        self, info: Info, input: CreateModelEndpointInput
    ) -> MutationResponse[TypeModelEndpoint]:
        """Create a new model endpoint."""
        user = info.context.user

        try:
            model = AIModel.objects.get(id=input.model_id)
        except AIModel.DoesNotExist:
            raise DjangoValidationError(f"AI Model with ID {input.model_id} does not exist.")

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_change:
                    raise DjangoValidationError(
                        "You don't have permission to add endpoints to this model."
                    )
            else:
                raise DjangoValidationError(
                    "You don't have permission to add endpoints to this model."
                )

        # If this is primary, unset other primary endpoints
        if input.is_primary:
            ModelEndpoint.objects.filter(model=model, is_primary=True).update(is_primary=False)

        endpoint = ModelEndpoint.objects.create(
            model=model,
            url=input.url,
            http_method=input.http_method,
            auth_type=input.auth_type,
            auth_header_name=input.auth_header_name,
            headers=input.headers or {},
            request_template=input.request_template or {},
            response_path=input.response_path or "",
            timeout_seconds=input.timeout_seconds,
            max_retries=input.max_retries,
            is_primary=input.is_primary,
            rate_limit_per_minute=input.rate_limit_per_minute,
            is_active=input.is_active,
        )

        return MutationResponse.success_response(TypeModelEndpoint.from_django(endpoint))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="update_model_endpoint",
        trace_attributes={"component": "aimodel"},
        track_activity={
            "verb": "updated endpoint",
            "get_data": lambda result, **kwargs: {
                "endpoint_id": str(result.id),
                "model_id": str(result.model.id),
            },
        },
    )
    def update_model_endpoint(
        self, info: Info, input: UpdateModelEndpointInput
    ) -> MutationResponse[TypeModelEndpoint]:
        """Update a model endpoint."""
        user = info.context.user

        try:
            endpoint = ModelEndpoint.objects.get(id=input.id)
        except ModelEndpoint.DoesNotExist:
            raise DjangoValidationError(f"Model Endpoint with ID {input.id} does not exist.")

        model = endpoint.model

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_change:
                    raise DjangoValidationError(
                        "You don't have permission to update this endpoint."
                    )
            else:
                raise DjangoValidationError("You don't have permission to update this endpoint.")

        # Update fields
        if input.url is not None:
            endpoint.url = input.url
        if input.http_method is not None:
            endpoint.http_method = input.http_method
        if input.auth_type is not None:
            endpoint.auth_type = input.auth_type
        if input.auth_header_name is not None:
            endpoint.auth_header_name = input.auth_header_name
        if input.headers is not None:
            endpoint.headers = input.headers
        if input.request_template is not None:
            endpoint.request_template = input.request_template
        if input.response_path is not None:
            endpoint.response_path = input.response_path
        if input.timeout_seconds is not None:
            endpoint.timeout_seconds = input.timeout_seconds
        if input.max_retries is not None:
            endpoint.max_retries = input.max_retries
        if input.is_active is not None:
            endpoint.is_active = input.is_active
        if input.rate_limit_per_minute is not None:
            endpoint.rate_limit_per_minute = input.rate_limit_per_minute

        # If setting as primary, unset other primary endpoints
        if input.is_primary is not None and input.is_primary:
            ModelEndpoint.objects.filter(model=model, is_primary=True).exclude(
                id=endpoint.id
            ).update(is_primary=False)
            endpoint.is_primary = True

        endpoint.save()
        return MutationResponse.success_response(TypeModelEndpoint.from_django(endpoint))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="delete_model_endpoint",
        trace_attributes={"component": "aimodel"},
        track_activity={
            "verb": "deleted endpoint",
            "get_data": lambda result, **kwargs: {
                "endpoint_id": str(kwargs.get("endpoint_id")),
                "success": result,
            },
        },
    )
    def delete_model_endpoint(self, info: Info, endpoint_id: int) -> MutationResponse[bool]:
        """Delete a model endpoint."""
        user = info.context.user

        try:
            endpoint = ModelEndpoint.objects.get(id=endpoint_id)
        except ModelEndpoint.DoesNotExist:
            raise DjangoValidationError(f"Model Endpoint with ID {endpoint_id} does not exist.")

        model = endpoint.model

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_delete:
                    raise DjangoValidationError(
                        "You don't have permission to delete this endpoint."
                    )
            else:
                raise DjangoValidationError("You don't have permission to delete this endpoint.")

        endpoint.delete()
        return MutationResponse.success_response(True)

    # ==================== VERSION MUTATIONS ====================

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="create_ai_model_version",
        trace_attributes={"component": "aimodel"},
    )
    def create_ai_model_version(
        self, info: Info, input: CreateAIModelVersionInput
    ) -> MutationResponse[TypeAIModelVersion]:
        """Create a new AI model version. Optionally copy providers from another version."""
        user = info.context.user

        try:
            model = AIModel.objects.get(id=input.model_id)
        except AIModel.DoesNotExist:
            raise DjangoValidationError(f"AI Model with ID {input.model_id} does not exist.")

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_change:
                    raise DjangoValidationError(
                        "You don't have permission to add versions to this model."
                    )
            else:
                raise DjangoValidationError(
                    "You don't have permission to add versions to this model."
                )

        # Create the version
        version = AIModelVersion.objects.create(
            ai_model=model,
            version=input.version,
            version_notes=input.version_notes or "",
            lifecycle_stage=input.lifecycle_stage.value if input.lifecycle_stage else "DEVELOPMENT",  # type: ignore[misc]
            supports_streaming=input.supports_streaming,
            max_tokens=input.max_tokens,
            supported_languages=input.supported_languages or [],
            input_schema=input.input_schema or {},
            output_schema=input.output_schema or {},
            metadata=input.metadata or {},
            status="DRAFT",
            is_latest=input.is_latest if input.is_latest is not None else True,
        )

        # If copy_from_version_id is provided, copy all providers
        if input.copy_from_version_id:
            try:
                source_version = AIModelVersion.objects.get(id=input.copy_from_version_id)
                version.copy_providers_from(source_version)
            except AIModelVersion.DoesNotExist:
                pass  # Silently ignore if source version doesn't exist

        return MutationResponse.success_response(TypeAIModelVersion.from_django(version))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="update_ai_model_version",
        trace_attributes={"component": "aimodel"},
    )
    def update_ai_model_version(
        self, info: Info, input: UpdateAIModelVersionInput
    ) -> MutationResponse[TypeAIModelVersion]:
        """Update an AI model version."""
        user = info.context.user

        try:
            version = AIModelVersion.objects.get(id=input.id)
        except AIModelVersion.DoesNotExist:
            raise DjangoValidationError(f"AI Model Version with ID {input.id} does not exist.")

        model = version.ai_model

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_change:
                    raise DjangoValidationError("You don't have permission to update this version.")
            else:
                raise DjangoValidationError("You don't have permission to update this version.")

        # Update fields
        if input.version is not None:
            version.version = input.version
        if input.version_notes is not None:
            version.version_notes = input.version_notes
        if input.lifecycle_stage is not None:
            version.lifecycle_stage = input.lifecycle_stage.value  # type: ignore[misc]
        if input.supports_streaming is not None:
            version.supports_streaming = input.supports_streaming
        if input.max_tokens is not None:
            version.max_tokens = input.max_tokens
        if input.supported_languages is not None:
            version.supported_languages = input.supported_languages
        if input.input_schema is not None:
            version.input_schema = input.input_schema
        if input.output_schema is not None:
            version.output_schema = input.output_schema
        if input.metadata is not None:
            version.metadata = input.metadata
        if input.status is not None:
            version.status = input.status
        if input.is_latest is not None:
            version.is_latest = input.is_latest

        version.save()
        return MutationResponse.success_response(TypeAIModelVersion.from_django(version))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="delete_ai_model_version",
        trace_attributes={"component": "aimodel"},
    )
    def delete_ai_model_version(self, info: Info, version_id: int) -> MutationResponse[bool]:
        """Delete an AI model version."""
        user = info.context.user

        try:
            version = AIModelVersion.objects.get(id=version_id)
        except AIModelVersion.DoesNotExist:
            raise DjangoValidationError(f"AI Model Version with ID {version_id} does not exist.")

        model = version.ai_model

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_delete:
                    raise DjangoValidationError("You don't have permission to delete this version.")
            else:
                raise DjangoValidationError("You don't have permission to delete this version.")

        version.delete()
        return MutationResponse.success_response(True)

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="publish_ai_model_version",
        trace_attributes={"component": "aimodel"},
    )
    def publish_ai_model_version(
        self, info: Info, version_id: int
    ) -> MutationResponse[TypeAIModelVersion]:
        """Publish an AI model version and set it as latest."""
        user = info.context.user

        try:
            version = AIModelVersion.objects.get(id=version_id)
        except AIModelVersion.DoesNotExist:
            raise DjangoValidationError(f"AI Model Version with ID {version_id} does not exist.")

        model = version.ai_model

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_change:
                    raise DjangoValidationError(
                        "You don't have permission to publish this version."
                    )
            else:
                raise DjangoValidationError("You don't have permission to publish this version.")

        from django.utils import timezone

        version.status = "ACTIVE"
        version.is_latest = True
        version.published_at = timezone.now()
        version.save()

        return MutationResponse.success_response(TypeAIModelVersion.from_django(version))

    # ==================== PROVIDER MUTATIONS ====================

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="create_version_provider",
        trace_attributes={"component": "aimodel"},
    )
    def create_version_provider(
        self, info: Info, input: CreateVersionProviderInput
    ) -> MutationResponse[TypeVersionProvider]:
        """Create a new provider for a version."""
        user = info.context.user

        try:
            version = AIModelVersion.objects.get(id=input.version_id)
        except AIModelVersion.DoesNotExist:
            raise DjangoValidationError(
                f"AI Model Version with ID {input.version_id} does not exist."
            )

        model = version.ai_model

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_change:
                    raise DjangoValidationError(
                        "You don't have permission to add providers to this version."
                    )
            else:
                raise DjangoValidationError(
                    "You don't have permission to add providers to this version."
                )

        provider = VersionProvider.objects.create(
            version=version,
            provider=input.provider,
            provider_model_id=input.provider_model_id or "",
            is_primary=input.is_primary,
            is_active=input.is_active,
            hf_use_pipeline=input.hf_use_pipeline,
            hf_auth_token=input.hf_auth_token,
            hf_model_class=input.hf_model_class,
            hf_attn_implementation=input.hf_attn_implementation or "flash_attention_2",
            framework=input.framework,
            config=input.config or {},
        )

        return MutationResponse.success_response(TypeVersionProvider.from_django(provider))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="update_version_provider",
        trace_attributes={"component": "aimodel"},
    )
    def update_version_provider(
        self, info: Info, input: UpdateVersionProviderInput
    ) -> MutationResponse[TypeVersionProvider]:
        """Update a version provider."""
        user = info.context.user

        try:
            provider = VersionProvider.objects.get(id=input.id)
        except VersionProvider.DoesNotExist:
            raise DjangoValidationError(f"Version Provider with ID {input.id} does not exist.")

        model = provider.version.ai_model

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_change:
                    raise DjangoValidationError(
                        "You don't have permission to update this provider."
                    )
            else:
                raise DjangoValidationError("You don't have permission to update this provider.")

        # Update fields
        if input.provider_model_id is not None:
            provider.provider_model_id = input.provider_model_id
        if input.is_primary is not None:
            provider.is_primary = input.is_primary
        if input.is_active is not None:
            provider.is_active = input.is_active
        if input.hf_use_pipeline is not None:
            provider.hf_use_pipeline = input.hf_use_pipeline
        if input.hf_auth_token is not None:
            provider.hf_auth_token = input.hf_auth_token
        if input.hf_model_class is not None:
            provider.hf_model_class = input.hf_model_class
        if input.hf_attn_implementation is not None:
            provider.hf_attn_implementation = input.hf_attn_implementation
        if input.framework is not None:
            provider.framework = input.framework
        if input.config is not None:
            provider.config = input.config

        provider.save()
        return MutationResponse.success_response(TypeVersionProvider.from_django(provider))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="delete_version_provider",
        trace_attributes={"component": "aimodel"},
    )
    def delete_version_provider(self, info: Info, provider_id: int) -> MutationResponse[bool]:
        """Delete a version provider."""
        user = info.context.user

        try:
            provider = VersionProvider.objects.get(id=provider_id)
        except VersionProvider.DoesNotExist:
            raise DjangoValidationError(f"Version Provider with ID {provider_id} does not exist.")

        model = provider.version.ai_model

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_delete:
                    raise DjangoValidationError(
                        "You don't have permission to delete this provider."
                    )
            else:
                raise DjangoValidationError("You don't have permission to delete this provider.")

        provider.delete()
        return MutationResponse.success_response(True)

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="set_primary_provider",
        trace_attributes={"component": "aimodel"},
    )
    def set_primary_provider(
        self, info: Info, provider_id: int
    ) -> MutationResponse[TypeVersionProvider]:
        """Set a provider as the primary provider for its version."""
        user = info.context.user

        try:
            provider = VersionProvider.objects.get(id=provider_id)
        except VersionProvider.DoesNotExist:
            raise DjangoValidationError(f"Version Provider with ID {provider_id} does not exist.")

        model = provider.version.ai_model

        # Check permissions
        if not user.is_superuser and model.user != user:
            if model.organization:
                org_member = OrganizationMembership.objects.filter(
                    user=user, organization=model.organization
                ).first()
                if not org_member or not org_member.role.can_change:
                    raise DjangoValidationError(
                        "You don't have permission to update this provider."
                    )
            else:
                raise DjangoValidationError("You don't have permission to update this provider.")

        provider.is_primary = True
        provider.save()  # The save method will unset other primaries

        return MutationResponse.success_response(TypeVersionProvider.from_django(provider))
