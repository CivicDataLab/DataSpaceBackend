"""Schema definitions for use cases."""

import datetime
import uuid
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Dataset, Metadata, Sector, Tag, UseCase, UseCaseMetadata
from api.types.type_dataset import TypeDataset
from api.types.type_usecase import TypeUseCase
from api.utils.enums import UseCaseStatus
from api.utils.graphql_telemetry import trace_resolver


@strawberry_django.input(UseCase, fields="__all__", exclude=["datasets", "slug"])
class UseCaseInput:
    """Input type for use case creation."""

    pass


@strawberry.input
class UCMetadataItemType:
    id: str
    value: str


@strawberry.input
class UpdateUseCaseMetadataInput:
    id: str
    metadata: List[UCMetadataItemType]
    summary: Optional[str]
    tags: Optional[List[str]]
    sectors: List[uuid.UUID]


@strawberry_django.partial(UseCase, fields="__all__", exclude=["datasets"])
class UseCaseInputPartial:
    """Input type for use case updates."""

    id: str
    slug: auto
    summary: auto


@strawberry.type(name="Query")
class Query:
    """Queries for use cases."""

    use_cases: list[TypeUseCase] = strawberry_django.field()
    use_case: TypeUseCase = strawberry_django.field()

    @strawberry_django.field
    @trace_resolver(
        name="get_datasets_by_use_case", attributes={"component": "usecase"}
    )
    def dataset_by_use_case(self, info: Info, use_case_id: str) -> list[TypeDataset]:
        """Get datasets by use case."""
        queryset = Dataset.objects.filter(usecase__id=use_case_id)
        return TypeDataset.from_django_list(queryset)


@trace_resolver(name="update_usecase_tags", attributes={"component": "usecase"})
def _update_usecase_tags(usecase: UseCase, tags: List[str]) -> None:
    usecase.tags.clear()
    for tag in tags:
        usecase.tags.add(
            Tag.objects.get_or_create(defaults={"value": tag}, value__iexact=tag)[0]
        )
    usecase.save()


@trace_resolver(name="update_usecase_sectors", attributes={"component": "usecase"})
def _update_usecase_sectors(usecase: UseCase, sectors: List[uuid.UUID]) -> None:
    sectors_objs = Sector.objects.filter(id__in=sectors)
    usecase.sectors.clear()
    usecase.sectors.add(*sectors_objs)
    usecase.save()


@trace_resolver(
    name="add_update_usecase_metadata",
    attributes={"component": "usecase", "operation": "mutation"},
)
def _add_update_usecase_metadata(
    usecase: UseCase, metadata_input: List[UCMetadataItemType]
) -> None:
    if not metadata_input or len(metadata_input) == 0:
        return
    _delete_existing_metadata(usecase)
    for metadata_input_item in metadata_input:
        try:
            metadata_field = Metadata.objects.get(id=metadata_input_item.id)
            if not metadata_field.enabled:
                _delete_existing_metadata(usecase)
                raise ValueError(
                    f"Metadata with ID {metadata_input_item.id} is not enabled."
                )
            uc_metadata = UseCaseMetadata(
                usecase=usecase,
                metadata_item=metadata_field,
                value=metadata_input_item.value,
            )
            uc_metadata.save()
        except Metadata.DoesNotExist:
            _delete_existing_metadata(usecase)
            raise ValueError(
                f"Metadata with ID {metadata_input_item.id} does not exist."
            )


@trace_resolver(name="delete_existing_metadata", attributes={"component": "usecase"})
def _delete_existing_metadata(usecase: UseCase) -> None:
    try:
        existing_metadata = UseCaseMetadata.objects.filter(usecase=usecase)
        existing_metadata.delete()
    except UseCaseMetadata.DoesNotExist:
        pass


@strawberry.type
class Mutation:
    """Mutations for use cases."""

    create_use_case: TypeUseCase = mutations.create(UseCaseInput)
    update_use_case: TypeUseCase = mutations.update(UseCaseInputPartial, key_attr="id")

    @strawberry_django.mutation(handle_django_errors=True)
    def add_use_case(self, info: Info) -> TypeUseCase:
        """Add a new use case."""
        use_case = UseCase.objects.create(
            title=f"New use_case {datetime.datetime.now().strftime('%d %b %Y - %H:%M')}"
        )
        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="add_update_usecase_metadata",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def add_update_usecase_metadata(
        self, update_metadata_input: UpdateUseCaseMetadataInput
    ) -> TypeUseCase:
        usecase_id = update_metadata_input.id
        metadata_input = update_metadata_input.metadata
        try:
            usecase = UseCase.objects.get(id=usecase_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {usecase_id} does not exist.")

        if update_metadata_input.summary:
            usecase.summary = update_metadata_input.summary
            usecase.save()
        if update_metadata_input.tags is not None:
            _update_usecase_tags(usecase, update_metadata_input.tags)
        _add_update_usecase_metadata(usecase, metadata_input)
        _update_usecase_sectors(usecase, update_metadata_input.sectors)
        return TypeUseCase.from_django(usecase)

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_use_case(self, info: Info, use_case_id: str) -> bool:
        """Delete a use case."""
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")
        use_case.delete()
        return True

    @strawberry_django.mutation(handle_django_errors=True)
    def add_dataset_to_use_case(
        self, info: Info, use_case_id: str, dataset_id: uuid.UUID
    ) -> TypeUseCase:
        """Add a dataset to a use case."""
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")

        use_case.datasets.add(dataset)
        use_case.save()
        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(handle_django_errors=True)
    def remove_dataset_from_use_case(
        self, info: Info, use_case_id: str, dataset_id: uuid.UUID
    ) -> TypeUseCase:
        """Remove a dataset from a use case."""
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")

        use_case.datasets.remove(dataset)
        use_case.save()
        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_usecase_datasets(
        self, info: Info, use_case_id: str, dataset_ids: List[uuid.UUID]
    ) -> TypeUseCase:
        """Update the datasets of a use case."""
        try:
            datasets = Dataset.objects.filter(id__in=dataset_ids)
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")

        use_case.datasets.set(datasets)
        use_case.save()
        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(handle_django_errors=True)
    def publish_use_case(self, info: Info, use_case_id: str) -> TypeUseCase:
        """Publish a use case."""
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")

        use_case.status = UseCaseStatus.PUBLISHED.value
        use_case.save()
        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(handle_django_errors=True)
    def unpublish_use_case(self, info: Info, use_case_id: str) -> TypeUseCase:
        """Un-publish a use case."""
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")

        use_case.status = UseCaseStatus.DRAFT.value
        use_case.save()
        return TypeUseCase.from_django(use_case)
