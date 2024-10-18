import uuid

import strawberry
import strawberry_django
from strawberry import auto
from strawberry_django import NodeInput
from strawberry_django.mutations import mutations

from api.utils.enums import UseCaseStatus
from api.models import UseCase, Dataset
from api.types.type_usecase import TypeUseCase


@strawberry_django.input(UseCase, fields="__all__", exclude=["datasets", "slug"])
class UseCaseInput:
    pass


@strawberry_django.partial(UseCase, fields="__all__", exclude=["datasets"])
class UseCaseInputPartial:
    id: str
    slug: auto


@strawberry.type(name="Query")
class Query:
    use_cases: list[TypeUseCase] = strawberry_django.field()


@strawberry.type
class Mutation:
    create_use_case: TypeUseCase = mutations.create(UseCaseInput)
    update_use_case: TypeUseCase = mutations.update(UseCaseInputPartial, key_attr="id")

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_use_case(self, use_case_id: str) -> bool:
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist as e:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")
        use_case.delete()
        return True

    @strawberry_django.mutation(handle_django_errors=True)
    def add_dataset_to_use_case(self, info, use_case_id: int, dataset_id: uuid.UUID) -> TypeUseCase:
        """
        Adds a dataset to a use case.
        """
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        use_case = UseCase.objects.get(id=use_case_id)
        use_case.datasets.add(dataset_id)
        use_case.save()
        return use_case

    @strawberry_django.mutation(handle_django_errors=True)
    def remove_dataset_from_use_case(self, info, use_case_id: int, dataset_id: uuid.UUID) -> TypeUseCase:
        """
        Removes a dataset from a use case.
        """
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        use_case = UseCase.objects.get(id=use_case_id)
        use_case.datasets.remove(dataset_id)
        use_case.save()
        return use_case

    @strawberry_django.mutation(handle_django_errors=True)
    def update_usecase_datasets(self, info, use_case_id: int, dataset_ids: list[uuid.UUID]) -> TypeUseCase:
        """
        Updates the datasets of a use case.
        """
        datasets = Dataset.objects.filter(id__in=dataset_ids)
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist as e:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")
        use_case.datasets = datasets
        use_case.save()
        return use_case

    @strawberry_django.mutation(handle_django_errors=True)
    def publish_use_case(self, info, use_case_id: int) -> TypeUseCase:
        """
        Publishes a use case.
        """
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist as e:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")
        use_case.status = UseCaseStatus.PUBLISHED
        use_case.save()
        return use_case

    @strawberry_django.mutation(handle_django_errors=True)
    def unpublish_use_case(self, info, use_case_id: int) -> TypeUseCase:
        """
        Unpublishes a use case.
        """
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist as e:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")
        use_case.status = UseCaseStatus.DRAFT
        use_case.save()
        return use_case

    @strawberry_django.mutation(handle_django_errors=True)
    def archive_use_case(self, info, use_case_id: int) -> TypeUseCase:
        """
        Archives a use case.
        """
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist as e:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")
        use_case.status = UseCaseStatus.ARCHIVED
        use_case.save()
        return use_case

