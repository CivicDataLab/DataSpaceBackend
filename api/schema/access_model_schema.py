import json
import os
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import requests
import strawberry
import strawberry_django
from strawberry.scalars import JSON
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
PARAKH_API_BASE_URL= os.environ["PARAKH_API_BASE_URL"]
RESOURCE_ENDPOINT = os.environ["RESOURCE_ENDPOINT"]


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
    
    # @strawberry.field
    # def access_model_data(self, info: Info, access_model_id: uuid.UUID) -> JSON:
    #     """
    #     Fetches and filters data from Parakh API based on an AccessModel.
    #     """
    #     user = info.context.user
    #     if not user.is_authenticated:
    #         raise Exception("Authentication required to access data.")

    #     try:
    #         jwt_token = info.context.auth_token
    #         access_model = AccessModel.objects.get(id=access_model_id)
            
    #         if access_model.type != AccessTypes.PUBLIC and (not hasattr(user, 'organization_id') or access_model.organization_id != user.organization_id):
    #              raise Exception("Not authorized to access data via this Access Model.")

    #         am_resources = AccessModelResource.objects.filter(
    #             access_model=access_model
    #         ).select_related('resource')

    #         result = {}
    #         headers = {
    #             "Authorization": f"Bearer {jwt_token}",
    #             "Accept": "application/json",
    #         }
            
    #         for amr in am_resources:
    #             resource_endpoint = amr.resource.external_endpoint 
    #             allowed_fields = list(amr.fields.values_list('field_name', flat=True))

    #             api_url = f"{PARAKH_API_BASE_URL}/{resource_endpoint}"
    #             response = requests.get(api_url, headers=headers)
    #             response.raise_for_status()
    #             model_data = response.json()
    #             if not isinstance(model_data, list):
    #                 model_data = [model_data] 
    #             filtered_model_data = []
    #             for model in model_data:
    #                 filtered_model = {
    #                     field: model.get(field)
    #                     for field in allowed_fields if field in model
    #                 }
    #                 filtered_model_data.append(filtered_model)
                
    #             result[resource_endpoint] = filtered_model_data
    #         return [TypeAccessModel.from_django(model) for model in model_data]

    #     except AccessModel.DoesNotExist:
    #         raise Exception(f"Access Model with ID {access_model_id} not found.")

    @strawberry_django.field
    def request_audit_from_parakh(info: Any, model_id: strawberry.ID, audit_name: str, audit_type: str, configuration: JSON, test_dataset_id: Optional[int] = None) -> JSON: # type: ignore
        """
        Sends a GraphQL mutation to ParakhAI to request a new audit.
        """
        if hasattr(info.context.user, 'auth_token') and info.context.user.auth_token:
            JWT_TOKEN = info.context.user.auth_token
        else:
            JWT_TOKEN = "SYSTEM_AUDIT_TOKEN"

        API_URL = f"{PARAKH_API_BASE_URL}/{RESOURCE_ENDPOINT}" 

        audit_input_variables = {
            "modelId": str(model_id),
            "name": audit_name,
            "auditType": audit_type,
            "testDatasetId": test_dataset_id,
            "configuration": configuration if configuration is not None else {}
        }

        variables = {"input": audit_input_variables}
        mutation_query = """
        mutation RequestAuditMutation($input: RequestAuditInput!) {
        requestAudit(input: $input) {
            success
            message
            audit {
            id
            status
            name
            }
        }
        }
        """
        HEADERS = {
            "Authorization": f"Bearer {JWT_TOKEN}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                API_URL,
                headers=HEADERS,
                json={'query': mutation_query, 'variables': variables}
            )
            response.raise_for_status() 
            
            response_data = response.json()
            if 'errors' in response_data:
                raise Exception(f"GraphQL API returned errors: {response_data['errors']}")
            result_object = response_data['data']['requestAudit']
            return json.dumps(result_object)
        
        except requests.exceptions.RequestException as e:
            status_code = e.response.status_code if e.response else "N/A"
            error_text = e.response.text if e.response else str(e)
            raise Exception(f"HTTP Error calling Parakh request_audit (Status {status_code}): {error_text}")
            
        except Exception as e:
            raise Exception(f"An unexpected error occurred during audit request: {str(e)}")
    

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
