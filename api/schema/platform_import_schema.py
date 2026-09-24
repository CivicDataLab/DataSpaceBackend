"""GraphQL surface for link-only imports from third-party platforms.

- ``preview_platform_dataset`` fetches normalised metadata, no side effects.
- ``import_platform_dataset`` creates a DRAFT dataset with one EXTERNAL resource
  linking to the dataset page on the platform (files are not imported).

Both take the same organization/dataspace request headers as ``add_dataset``;
the imported dataset is owned the same way a manually created one would be.
"""

from typing import Optional

import strawberry
from strawberry.types import Info

from api.schema.base_mutation import (
    BaseMutation,
    GraphQLValidationError,
    MutationResponse,
)
from api.services.platform_import_service import (
    import_platform_dataset,
    preview_platform_dataset,
)
from api.services.platform_importers import PlatformImportError
from api.types.type_dataset import TypeDataset
from api.types.type_dataset_source import (
    TypePlatformDatasetPreview,
    import_platform_enum,
)
from api.utils.graphql_telemetry import trace_resolver
from authorization.graphql_permissions import IsAuthenticated
from authorization.permissions import CreateDatasetPermission


@strawberry.input
class ImportPlatformDatasetInput:
    platform: import_platform_enum  # type: ignore
    #: Short id ("owner/name") or a pasted platform URL.
    identifier: str
    #: Optional display title on DataSpace; defaults to the platform's title.
    title: Optional[str] = None


@strawberry.type
class Query:
    @strawberry.field(permission_classes=[IsAuthenticated])
    @trace_resolver(name="preview_platform_dataset", attributes={"component": "platform_import"})
    def preview_platform_dataset(
        self, info: Info, platform: import_platform_enum, identifier: str  # type: ignore
    ) -> TypePlatformDatasetPreview:
        """Look up a Hugging Face / GitHub / Kaggle dataset and show what an import would create."""
        try:
            data = preview_platform_dataset(platform.value, identifier)
        except PlatformImportError as exc:
            # Surface the importer's user-safe message as a GraphQL error.
            raise ValueError(exc.message) from exc
        return TypePlatformDatasetPreview.from_info(data)


@strawberry.type
class Mutation:
    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated, CreateDatasetPermission],
        trace_name="import_platform_dataset",
        trace_attributes={"component": "platform_import"},
        track_activity={
            "verb": "imported",
            "get_data": lambda result, import_input=None, **kwargs: {
                "dataset_id": str(result.id),
                "dataset_title": result.title,
                "platform": import_input.platform.value if import_input else None,
                "identifier": import_input.identifier if import_input else None,
                "organization": (str(result.organization.id) if result.organization else None),
            },
        },
    )
    def import_platform_dataset(
        self, info: Info, import_input: ImportPlatformDatasetInput
    ) -> MutationResponse[TypeDataset]:
        """Create a DRAFT dataset that links to the dataset on the platform."""
        organization = info.context.context.get("organization")
        dataspace = info.context.context.get("dataspace")
        user = info.context.user

        try:
            dataset = import_platform_dataset(
                platform=import_input.platform.value,
                identifier=import_input.identifier,
                user=user,
                organization=organization,
                dataspace=dataspace,
                title=import_input.title,
            )
        except PlatformImportError as exc:
            return MutationResponse.error_response(GraphQLValidationError.from_message(exc.message))

        return MutationResponse.success_response(TypeDataset.from_django(dataset))
