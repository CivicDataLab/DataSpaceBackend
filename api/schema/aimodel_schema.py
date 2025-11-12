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
from api.models.Dataset import Tag
from api.schema.base_mutation import BaseMutation, MutationResponse
from api.schema.extensions import TrackActivity, TrackModelActivity
from api.types.type_aimodel import (
    AIModelFilter,
    AIModelOrder,
    AIModelProviderEnum,
    AIModelStatusEnum,
    AIModelTypeEnum,
    EndpointAuthTypeEnum,
    EndpointHTTPMethodEnum,
    TypeAIModel,
    TypeModelEndpoint,
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
        model.tags.add(
            Tag.objects.get_or_create(defaults={"value": tag}, value__iexact=tag)[0]
        )
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


def _update_aimodel_geographies(model: AIModel, geographies: List[str]) -> None:
    """Helper function to update geographies for an AI model."""
    from api.models import Geography

    model.geographies.clear()
    for geography_name in geographies:
        try:
            geography = Geography.objects.get(name__iexact=geography_name)
            model.geographies.add(geography)
        except Geography.DoesNotExist:
            pass
    model.save()


@strawberry.input
class CreateAIModelInput:
    """Input for creating a new AI Model."""

    name: str
    display_name: str
    description: str
    model_type: AIModelTypeEnum
    provider: AIModelProviderEnum
    version: Optional[str] = None
    provider_model_id: Optional[str] = None
    supports_streaming: bool = False
    max_tokens: Optional[int] = None
    supported_languages: Optional[List[str]] = None
    input_schema: Optional[strawberry.scalars.JSON] = None
    output_schema: Optional[strawberry.scalars.JSON] = None
    tags: Optional[List[str]] = None
    sectors: Optional[List[str]] = None
    geographies: Optional[List[str]] = None
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
    geographies: Optional[List[str]] = None
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
                    queryset = AIModel.objects.filter(
                        user=user
                    ) | AIModel.objects.filter(is_public=True, is_active=True)
            else:
                # For non-authenticated users, only show public active models
                queryset = AIModel.objects.filter(is_public=True, is_active=True)

        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return TypeAIModel.from_django_list(list(queryset.distinct()))

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
                "organization": (
                    str(result.organization.id) if result.organization else None
                ),
            },
        },
    )
    def create_ai_model(
        self, info: Info, input: CreateAIModelInput
    ) -> MutationResponse[TypeAIModel]:
        """Create a new AI model."""
        organization = info.context.context.get("organization")
        user = info.context.user

        # Prepare supported_languages
        supported_languages = input.supported_languages or []

        # Prepare schemas
        input_schema = input.input_schema or {}
        output_schema = input.output_schema or {}

        # Prepare metadata
        metadata = input.metadata or {}

        try:
            model = AIModel.objects.create(
                name=input.name,
                display_name=input.display_name,
                version=input.version or "",
                description=input.description,
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
                "organization": (
                    str(result.organization.id) if result.organization else None
                ),
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
                    raise DjangoValidationError(
                        "You don't have permission to update this model."
                    )
            else:
                raise DjangoValidationError(
                    "You don't have permission to update this model."
                )

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
                    raise DjangoValidationError(
                        "You don't have permission to delete this model."
                    )
            else:
                raise DjangoValidationError(
                    "You don't have permission to delete this model."
                )

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
            raise DjangoValidationError(
                f"AI Model with ID {input.model_id} does not exist."
            )

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
            ModelEndpoint.objects.filter(model=model, is_primary=True).update(
                is_primary=False
            )

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

        return MutationResponse.success_response(
            TypeModelEndpoint.from_django(endpoint)
        )

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
            raise DjangoValidationError(
                f"Model Endpoint with ID {input.id} does not exist."
            )

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
                raise DjangoValidationError(
                    "You don't have permission to update this endpoint."
                )

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
        return MutationResponse.success_response(
            TypeModelEndpoint.from_django(endpoint)
        )

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
    def delete_model_endpoint(
        self, info: Info, endpoint_id: int
    ) -> MutationResponse[bool]:
        """Delete a model endpoint."""
        user = info.context.user

        try:
            endpoint = ModelEndpoint.objects.get(id=endpoint_id)
        except ModelEndpoint.DoesNotExist:
            raise DjangoValidationError(
                f"Model Endpoint with ID {endpoint_id} does not exist."
            )

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
                raise DjangoValidationError(
                    "You don't have permission to delete this endpoint."
                )

        endpoint.delete()
        return MutationResponse.success_response(True)
