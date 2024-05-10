import uuid
from enum import Enum
from typing import Optional

import strawberry
import strawberry_django

from api.models import AccessModel, AccessModelResource, Dataset, Resource
from api.types.type_access_model import TypeAccessModel


@strawberry.input
class AccessModelResourceInput:
    resource: uuid.UUID


# TODO extract strawberry enum from django textchoices
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

@strawberry.type(name="Query")
class Query:
    @strawberry_django.field
    def access_model_resources(self, info, dataset_id: uuid.UUID) -> list[TypeAccessModel]:
        return AccessModel.objects.filter(dataset_id=dataset_id)

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
        access_model.name = access_model_input.name
        access_model.description = access_model_input.description
        access_model.type = access_model_input.type
        access_model.save()
        for resource_input in access_model_input.resources:
            resource = AccessModelResource()
            resource.access_model = access_model
            resource_id = resource_input.resource
            try:
                dataset_resource = Resource.objects.get(id=resource_id)
            except Resource.DoesNotExist as e:
                raise ValueError(f"Resource with ID {resource_id} does not exist.")
            resource.resource = dataset_resource
            resource.save()
        return access_model
