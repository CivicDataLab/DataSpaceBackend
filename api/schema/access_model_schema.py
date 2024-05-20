import uuid
from enum import Enum
from typing import Optional

import strawberry
import strawberry_django

from api.models import AccessModel, AccessModelResource, Dataset, Resource, ResourceSchema
from api.types.type_access_model import TypeAccessModel

@strawberry.input
class AccessModelResourceInput:
    resource: uuid.UUID
    fields: list[int]


# TODO extract strawberry enum from django text choices
@strawberry.enum
class AccessTypes(Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    PROTECTED = "PROTECTED"


@strawberry.input
class AccessModelInput:
    dataset: uuid.UUID
    name: str
    description: Optional[str]
    type: AccessTypes
    resources: list[AccessModelResourceInput]


@strawberry.input
class EditAccessModelInput:
    access_model_id: uuid.UUID
    name: str
    description: Optional[str]
    type: AccessTypes
    resources: list[AccessModelResourceInput]


@strawberry.type(name="Query")
class Query:
    @strawberry_django.field
    def access_model_resources(self, info, dataset_id: uuid.UUID) -> list[TypeAccessModel]:
        return AccessModel.objects.filter(dataset_id=dataset_id)


def _add_resource_fields(access_model_resource: AccessModelResource, dataset_resource: Resource, fields: list[int]):
    for field_id in fields:
        try:
            dataset_field = dataset_resource.resourceschema_set.get(id=field_id)
        except (Resource.DoesNotExist, ResourceSchema.DoesNotExist) as e:
            raise ValueError(f"Field with ID {field_id} does not exist.")
        access_model_resource.fields.add(dataset_field)
    access_model_resource.save()


def _add_update_access_model_resources(access_model: AccessModel, model_input_resources):
    if access_model.accessmodelresource_set.exists():
        access_model.accessmodelresource_set.all().delete()
        access_model.save()
    for resource_input in model_input_resources:
        access_model_resource = AccessModelResource()
        access_model_resource.access_model = access_model
        resource_id = resource_input.resource
        try:
            dataset_resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {resource_id} does not exist.")
        access_model_resource.resource = dataset_resource
        access_model_resource.save()
        _add_resource_fields(access_model_resource, dataset_resource, resource_input.fields)


def _update_access_model_fields(access_model: AccessModel, access_model_input):
    access_model.name = access_model_input.name
    access_model.description = access_model_input.description
    access_model.type = access_model_input.type.value
    access_model.save()


@strawberry.type
class Mutation:

    @strawberry_django.mutation(handle_django_errors=True)
    def create_access_model(self, access_model_input: AccessModelInput) -> TypeAccessModel:
        access_model = AccessModel()
        dataset_id = access_model_input.dataset

        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        access_model.dataset = dataset
        _update_access_model_fields(access_model, access_model_input)
        model_input_resources = access_model_input.resources
        _add_update_access_model_resources(access_model, model_input_resources)
        return access_model

    @strawberry_django.mutation(handle_django_errors=True)
    def edit_access_model(self, access_model_input: EditAccessModelInput) -> TypeAccessModel:
        try:
            access_model = AccessModel.objects.get(id=access_model_input.access_model_id)
        except AccessModel.DoesNotExist as e:
            raise ValueError(f"Access model with ID {access_model_input.access_model_id} does not exist.")
        _update_access_model_fields(access_model, access_model_input)
        model_input_resources = access_model_input.resources
        _add_update_access_model_resources(access_model, model_input_resources)
        return access_model

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_access_model(self, access_model_id: uuid.UUID) -> bool:
        try:
            access_model = AccessModel.objects.get(id=access_model_id)
        except AccessModel.DoesNotExist as e:
            raise ValueError(f"Access model with ID {access_model_id} does not exist.")
        access_model.delete()
        return True
