import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import strawberry
import strawberry_django
from django.db.models import Q
from django.db.models.expressions import Combinable
from strawberry.types import Info

from api.models import (
    AccessModel,
    AccessModelResource,
    Dataset,
    Resource,
    ResourceSchema,
)
from api.types.type_access_model import TypeAccessModel
from api.utils.enums import AccessTypes

AccessTypesEnum = strawberry.enum(AccessTypes)  # type: ignore


@strawberry.input
class AccessModelResourceInput:
    resource: uuid.UUID
    fields: List[int]


@strawberry.input
class AccessModelInput:
    dataset: uuid.UUID
    name: str
    description: Optional[str]
    type: AccessTypesEnum
    resources: List[AccessModelResourceInput]


@strawberry.input
class EditAccessModelInput:
    access_model_id: Optional[uuid.UUID]
    dataset: uuid.UUID
    name: Optional[str]
    description: Optional[str]
    type: Optional[AccessTypesEnum]
    resources: Optional[List[AccessModelResourceInput]]


@strawberry.type(name="Query")
class Query:
    @strawberry_django.field
    def access_model_resources(
        self, info: Info, dataset_id: uuid.UUID
    ) -> List[TypeAccessModel]:
        models = AccessModel.objects.filter(dataset_id=dataset_id)
        return [TypeAccessModel.from_django(model) for model in models]

    @strawberry_django.field
    def access_model(self, info: Info, access_model_id: uuid.UUID) -> TypeAccessModel:
        model = AccessModel.objects.get(id=access_model_id)
        return TypeAccessModel.from_django(model)


def _add_resource_fields(
    access_model_resource: AccessModelResource,
    dataset_resource: Resource,
    fields: List[int],
) -> None:
    for field_id in fields:
        try:
            dataset_field = dataset_resource.resourceschema_set.get(id=field_id)
        except (Resource.DoesNotExist, ResourceSchema.DoesNotExist) as e:
            raise ValueError(f"Field with ID {field_id} does not exist.")
        access_model_resource.fields.add(dataset_field)
    access_model_resource.save()


def _add_update_access_model_resources(
    access_model: AccessModel,
    model_input_resources: Optional[List[AccessModelResourceInput]],
) -> None:
    if access_model.accessmodelresource_set.exists():
        access_model.accessmodelresource_set.all().delete()
        access_model.save()
    if not model_input_resources:
        return
    for resource_input in model_input_resources:
        try:
            dataset_resource = Resource.objects.get(id=resource_input.resource)
        except Resource.DoesNotExist as e:
            raise ValueError(
                f"Resource with ID {resource_input.resource} does not exist."
            )

        access_model_resource = AccessModelResource.objects.create(
            access_model=access_model, resource=dataset_resource
        )
        _add_resource_fields(
            access_model_resource, dataset_resource, resource_input.fields
        )


def _update_access_model_fields(
    access_model: AccessModel,
    access_model_input: Union[EditAccessModelInput, AccessModelInput],
) -> None:
    if hasattr(access_model_input, "name") and access_model_input.name:
        access_model.name = access_model_input.name
    if hasattr(access_model_input, "description"):
        access_model.description = access_model_input.description
    if hasattr(access_model_input, "type") and access_model_input.type:
        access_model.type = access_model_input.type
    access_model.save()


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def create_access_model(
        self, info: Info, access_model_input: AccessModelInput
    ) -> TypeAccessModel:
        try:
            dataset = Dataset.objects.get(id=access_model_input.dataset)
        except Dataset.DoesNotExist:
            raise ValueError(
                f"Dataset with ID {access_model_input.dataset} does not exist."
            )

        access_model = AccessModel.objects.create(
            dataset=dataset,
            name=access_model_input.name,
            description=access_model_input.description,
            type=access_model_input.type.value,
        )

        _update_access_model_fields(access_model, access_model_input)
        _add_update_access_model_resources(access_model, access_model_input.resources)
        return TypeAccessModel.from_django(access_model)

    @strawberry_django.mutation(handle_django_errors=True)
    def edit_access_model(
        self, info: Info, access_model_input: EditAccessModelInput
    ) -> TypeAccessModel:
        if not access_model_input.access_model_id:
            try:
                dataset = Dataset.objects.get(id=access_model_input.dataset)
            except Dataset.DoesNotExist as e:
                raise ValueError(
                    f"Dataset with ID {access_model_input.dataset} does not exist."
                )
            access_model = AccessModel.objects.create(dataset=dataset)
        else:
            try:
                access_model = AccessModel.objects.get(
                    id=access_model_input.access_model_id
                )
            except AccessModel.DoesNotExist as e:
                raise ValueError(
                    f"Access Model with ID {access_model_input.access_model_id} does not exist."
                )

        _update_access_model_fields(access_model, access_model_input)
        _add_update_access_model_resources(access_model, access_model_input.resources)
        return TypeAccessModel.from_django(access_model)

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_access_model(self, info: Info, access_model_id: uuid.UUID) -> bool:
        try:
            access_model = AccessModel.objects.get(id=access_model_id)
            access_model.delete()
            return True
        except AccessModel.DoesNotExist as e:
            raise ValueError(f"Access Model with ID {access_model_id} does not exist.")
