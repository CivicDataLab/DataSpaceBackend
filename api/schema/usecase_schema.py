"""Schema definitions for use cases."""

import datetime
import uuid
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Dataset, UseCase
from api.types.type_usecase import TypeUseCase
from api.utils.enums import UseCaseStatus


@strawberry_django.input(UseCase, fields="__all__", exclude=["datasets", "slug"])
class UseCaseInput:
    """Input type for use case creation."""

    pass


@strawberry_django.partial(UseCase, fields="__all__", exclude=["datasets"])
class UseCaseInputPartial:
    """Input type for use case updates."""

    id: str
    slug: auto


@strawberry.type(name="Query")
class Query:
    """Queries for use cases."""

    use_cases: list[TypeUseCase] = strawberry_django.field()
    use_case: TypeUseCase = strawberry_django.field()


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
