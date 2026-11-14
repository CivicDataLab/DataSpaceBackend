"""Upload, replace and delete through the GraphQL API, read through the data API.

Who may call these mutations is unchanged and covered by
tests/schema/test_resource_permissions.py; these tests follow a dataset owner
through the data-table lifecycle end to end.
"""

import types
from typing import Any, Dict

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from rest_framework.test import APIClient

from api.models import Resource, ResourceDataTable
from api.schema.schema import schema
from tests.data_index.support import fixture_bytes, uses_data_db

CREATE = """mutation ($ds: UUID!, $file: Upload!) {
  createFileResources(fileResourceInput: {dataset: $ds, files: [$file]}) { id }
}"""
REPLACE = """mutation ($id: UUID!, $file: Upload!) {
  updateFileResource(fileResourceInput: {id: $id, file: $file}) {
    __typename ... on OperationInfo { messages { message } }
  }
}"""
RESET = """mutation ($id: UUID!) {
  resetFileResourceSchema(resourceId: $id) {
    __typename ... on OperationInfo { messages { message } }
  }
}"""
DELETE_RESOURCE = "mutation ($id: UUID!) { deleteFileResource(resourceId: $id) }"
DELETE_DATASET = "mutation ($id: UUID!) { deleteDataset(datasetId: $id) }"


def run(user: Any, query: str, **variables: Any) -> Dict[str, Any]:
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    result = schema.execute_sync(query, variable_values=variables, context_value=ctx)
    assert result.errors is None, result.errors
    payload = next(iter(result.data.values()))
    if isinstance(payload, dict):
        assert payload.get("__typename") != "OperationInfo", payload
    return result.data


def csv_upload(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile("cases.csv", fixture_bytes(name), content_type="text/csv")


def data_api(owner: Any, resource_id: Any) -> Any:
    client = APIClient()
    client.force_authenticate(owner)
    return client.get(f"/api/resources/{resource_id}/data/?order_by=district")


def upload(owner: Any, dataset: Any, name: str) -> Resource:
    data = run(owner, CREATE, ds=str(dataset.id), file=csv_upload(name))
    return Resource.objects.get(id=data["createFileResources"][0]["id"])


@uses_data_db
def test_an_uploaded_csv_is_served_from_its_own_table(
    owner: Any, dataset: Any, tables: Any
) -> None:
    resource = upload(owner, dataset, "districts_v1.csv")

    table = ResourceDataTable.objects.get(resource=resource).table_name
    assert table.startswith("rdt_") and tables.exists(table)
    response = data_api(owner, resource.id)
    assert response.status_code == 200, response.content
    assert response.json()["rows"] == [["Jorhat", 30], ["Kamrup", 10], ["Nagaon", 20]]


@uses_data_db
def test_a_replaced_file_is_served_and_its_old_table_is_gone(
    owner: Any, dataset: Any, tables: Any
) -> None:
    resource = upload(owner, dataset, "districts_v1.csv")
    old_table = ResourceDataTable.objects.get(resource=resource).table_name

    run(owner, REPLACE, id=str(resource.id), file=csv_upload("districts_v2.csv"))

    assert not tables.exists(old_table)
    assert tables.names() == [ResourceDataTable.objects.get(resource=resource).table_name]
    assert data_api(owner, resource.id).json()["total"] == 4


@uses_data_db
def test_resetting_the_columns_switches_to_a_fresh_table(
    owner: Any, dataset: Any, tables: Any
) -> None:
    resource = upload(owner, dataset, "districts_v1.csv")
    old_table = ResourceDataTable.objects.get(resource=resource).table_name

    run(owner, RESET, id=str(resource.id))

    new_table = ResourceDataTable.objects.get(resource=resource).table_name
    assert new_table != old_table
    assert tables.names() == [new_table]
    assert data_api(owner, resource.id).json()["total"] == 3


@uses_data_db
def test_deleting_a_resource_removes_its_table_and_its_data(
    owner: Any, dataset: Any, tables: Any
) -> None:
    resource = upload(owner, dataset, "districts_v1.csv")

    run(owner, DELETE_RESOURCE, id=str(resource.id))

    assert tables.names() == []
    assert data_api(owner, resource.id).status_code == 404


@uses_data_db
def test_deleting_a_dataset_removes_every_table_it_had(
    owner: Any, dataset: Any, tables: Any
) -> None:
    upload(owner, dataset, "districts_v1.csv")
    upload(owner, dataset, "districts_v2.csv")
    assert len(tables.names()) == 2

    run(owner, DELETE_DATASET, id=str(dataset.id))

    assert tables.names() == []
