"""A refused access model request saves nothing (#316).

Root cause: `createAccessModel` created the access model, then checked its resources
(each must belong to the same dataset) and fields, with no transaction around it. A
refused resource raised after the row was saved, so an empty access model stayed on
the dataset. `editAccessModel` had the same shape and was worse: it deleted the access
model's existing resource links before adding the new ones, so a refused resource left
the model with none.

Fix: both mutations run inside `transaction.atomic()`, so a refused resource or field
undoes the whole request.
"""

import types

import pytest
from django.test import RequestFactory

from api.models import (
    AccessModel,
    AccessModelResource,
    Dataset,
    Resource,
    ResourceSchema,
)
from api.schema.schema import schema
from authorization.models import User

RESULT = "... on TypeAccessModel { id } ... on OperationInfo { messages { message } }"

CREATE = f"""
mutation ($d: UUID!, $resources: [AccessModelResourceInput!]!) {{
  createAccessModel(accessModelInput: {{
    dataset: $d, name: "new", description: null, type: PUBLIC, resources: $resources
  }}) {{ {RESULT} }}
}}
"""

EDIT = f"""
mutation ($a: UUID, $d: UUID!, $resources: [AccessModelResourceInput!]) {{
  editAccessModel(accessModelInput: {{
    accessModelId: $a, dataset: $d, name: "renamed", description: null, type: null,
    resources: $resources
  }}) {{ {RESULT} }}
}}
"""


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


def refused(result):
    return bool(result.errors) or "messages" in str(result.data)


@pytest.fixture
def world(db):
    owner = User.objects.create(username="owner", keycloak_id="owner")
    mine = Dataset.objects.create(title="A", slug="a", description="d", user=owner)
    other = Dataset.objects.create(title="B", slug="b", description="d", user=owner)
    own_file = Resource.objects.create(name="a.csv", dataset=mine)
    foreign_file = Resource.objects.create(name="b.csv", dataset=other)
    column = ResourceSchema.objects.create(resource=own_file, field_name="c", format="STRING")
    model = AccessModel.objects.create(name="kept", dataset=mine)
    link = AccessModelResource.objects.create(access_model=model, resource=own_file)
    return types.SimpleNamespace(
        owner=owner,
        mine=mine,
        own_file=own_file,
        foreign_file=foreign_file,
        column=column,
        model=model,
        link=link,
    )


def resource(file, fields=()):
    return {"resource": str(file.id), "fields": list(fields)}


# ─── Create ───────────────────────────────────────────────────────────────────


def test_create_with_another_datasets_file_saves_no_access_model(world):
    result = run(
        world.owner,
        CREATE,
        d=str(world.mine.id),
        resources=[resource(world.own_file), resource(world.foreign_file)],
    )

    assert refused(result)
    assert list(AccessModel.objects.filter(dataset=world.mine)) == [world.model]
    assert AccessModelResource.objects.count() == 1  # only the existing link


def test_create_with_an_unknown_field_saves_no_access_model(world):
    result = run(
        world.owner,
        CREATE,
        d=str(world.mine.id),
        resources=[resource(world.own_file, fields=[999999])],
    )

    assert refused(result)
    assert list(AccessModel.objects.filter(dataset=world.mine)) == [world.model]


def test_valid_create_still_saves(world):
    result = run(
        world.owner,
        CREATE,
        d=str(world.mine.id),
        resources=[resource(world.own_file, fields=[world.column.id])],
    )

    assert not refused(result), result
    created = AccessModel.objects.get(dataset=world.mine, name="new")
    assert list(created.accessmodelresource_set.values_list("resource", flat=True)) == [
        world.own_file.id
    ]


# ─── Edit ─────────────────────────────────────────────────────────────────────


def test_edit_with_another_datasets_file_keeps_existing_files_and_name(world):
    result = run(
        world.owner,
        EDIT,
        a=str(world.model.id),
        d=str(world.mine.id),
        resources=[resource(world.foreign_file)],
    )

    assert refused(result)
    world.model.refresh_from_db()
    assert world.model.name == "kept"
    assert list(world.model.accessmodelresource_set.all()) == [world.link]


def test_edit_without_an_id_and_a_refused_file_saves_no_access_model(world):
    result = run(
        world.owner,
        EDIT,
        a=None,
        d=str(world.mine.id),
        resources=[resource(world.foreign_file)],
    )

    assert refused(result)
    assert list(AccessModel.objects.filter(dataset=world.mine)) == [world.model]


def test_valid_edit_still_replaces_files(world):
    second = Resource.objects.create(name="a2.csv", dataset=world.mine)

    result = run(
        world.owner,
        EDIT,
        a=str(world.model.id),
        d=str(world.mine.id),
        resources=[resource(second)],
    )

    assert not refused(result), result
    world.model.refresh_from_db()
    assert world.model.name == "renamed"
    assert list(world.model.accessmodelresource_set.values_list("resource", flat=True)) == [
        second.id
    ]
