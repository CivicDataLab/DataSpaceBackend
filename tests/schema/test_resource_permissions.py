"""Resource mutations need edit rights on the dataset; drafts' resources are
visible only to people who can see the draft."""

import types
import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from api.models import Dataset, Organization, Resource
from api.schema.schema import schema
from authorization.models import DatasetPermission, OrganizationMembership, Role, User

DENIED = "You don't have permission to change this dataset's resources"


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def world(db):
    org = Organization.objects.create(name="Org", description="o", slug="org")
    other_org = Organization.objects.create(name="Other", description="o", slug="other-org")
    editor_role = Role.objects.create(name="editor", can_view=True, can_add=True, can_change=True)
    viewer_role = Role.objects.create(name="viewer", can_view=True)
    users = {
        name: User.objects.create(username=name, keycloak_id=name)
        for name in ["owner", "editor", "viewer", "outsider", "shared"]
    }
    users["admin"] = User.objects.create(username="admin", keycloak_id="admin", is_superuser=True)
    OrganizationMembership.objects.create(user=users["editor"], organization=org, role=editor_role)
    OrganizationMembership.objects.create(user=users["viewer"], organization=org, role=viewer_role)
    OrganizationMembership.objects.create(
        user=users["outsider"], organization=other_org, role=editor_role
    )
    draft = Dataset.objects.create(
        title="Draft", slug="draft", description="d", user=users["owner"], organization=org
    )
    published = Dataset.objects.create(
        title="Pub",
        slug="pub",
        description="d",
        user=users["owner"],
        organization=org,
        status="PUBLISHED",
    )
    DatasetPermission.objects.create(user=users["shared"], dataset=draft, role=editor_role)
    return types.SimpleNamespace(
        users=users,
        draft=draft,
        published=published,
        draft_res=Resource.objects.create(name="d.csv", dataset=draft),
        pub_res=Resource.objects.create(name="p.csv", dataset=published),
    )


DELETE = "mutation ($id: UUID!) { deleteFileResource(resourceId: $id) }"
RENAME = """mutation ($id: UUID!) {
  updateFileResource(fileResourceInput: {id: $id, name: "renamed"}) { ... on TypeResource { name } }
}"""
CREATE_EMPTY = """mutation ($ds: UUID!) {
  createFileResource(fileResourceInput: {dataset: $ds}) { ... on TypeResource { id } }
}"""
CREATE_FILES = """mutation ($ds: UUID!) {
  createFileResources(fileResourceInput: {dataset: $ds, files: []}) { id }
}"""
RESET_SCHEMA = """mutation ($id: UUID!) {
  resetFileResourceSchema(resourceId: $id) { ... on TypeResource { id } }
}"""
UPDATE_SCHEMA = """mutation ($id: UUID!) {
  updateFileResourceSchema(schemaUpdateInput: {resource: $id, updates: []}) {
    ... on TypeResource { id }
  }
}"""
MAJOR = """mutation ($id: UUID!) {
  createMajorVersion(input: {resourceId: $id, description: "x"}) { ... on TypeResource { id } }
}"""


def denied(result):
    """Either a top-level GraphQL error or a handled OperationInfo, both with DENIED."""
    if result.errors:
        return any(DENIED in str(e.message) for e in result.errors)
    payload = next(iter(result.data.values()))
    return bool(payload) and DENIED in str(payload.get("messages", payload))


@pytest.mark.parametrize("who", ["anonymous", "outsider", "viewer"])
@pytest.mark.parametrize(
    "query,arg",
    [
        (DELETE, "res"),
        (RENAME, "res"),
        (RESET_SCHEMA, "res"),
        (UPDATE_SCHEMA, "res"),
        (MAJOR, "res"),
        (CREATE_EMPTY, "ds"),
        (CREATE_FILES, "ds"),
    ],
)
def test_people_without_edit_rights_are_refused(world, who, query, arg):
    user = AnonymousUser() if who == "anonymous" else world.users[who]
    variables = {"id": str(world.pub_res.id)} if arg == "res" else {"ds": str(world.published.id)}
    if query in (RENAME, UPDATE_SCHEMA, RESET_SCHEMA, CREATE_EMPTY, MAJOR):
        query = query.replace("{ ... on TypeResource", "{ __typename ... on TypeResource")
        query = query.replace(
            "{ id } }\n}", "{ id } ... on OperationInfo { messages { message } } }\n}"
        )
        query = query.replace(
            "{ name } }\n}", "{ name } ... on OperationInfo { messages { message } } }\n}"
        )
    r = run(user, query, **variables)
    assert denied(r), (who, r.errors, r.data)
    assert Resource.objects.filter(id=world.pub_res.id, name="p.csv").exists()


@pytest.mark.parametrize("who", ["owner", "editor", "admin", "shared"])
def test_people_with_edit_rights_can_rename_and_delete(world, who):
    user = world.users[who]
    r = run(user, RENAME, id=str(world.draft_res.id))
    assert r.errors is None, r.errors
    assert r.data["updateFileResource"]["name"] == "renamed"

    r = run(user, DELETE, id=str(world.draft_res.id))
    assert r.errors is None and r.data["deleteFileResource"] is True
    assert not Resource.objects.filter(id=world.draft_res.id).exists()


def test_shared_editor_loses_rights_once_published(world):
    # Dataset-level roles only cover drafts, as for dataset edits.
    r = run(world.users["shared"], DELETE, id=str(world.pub_res.id))
    assert denied(r)


def test_missing_id_is_refused_like_a_forbidden_one(world):
    r = run(AnonymousUser(), DELETE, id=str(uuid.uuid4()))
    assert denied(r)
    assert "does not exist" not in str(r.errors)


LIST = "query ($ds: UUID!) { datasetResources(datasetId: $ds) { name } }"
ONE = "query ($id: UUID!) { resourceById(resourceId: $id) { name } }"


def test_published_resources_stay_public(world):
    r = run(AnonymousUser(), LIST, ds=str(world.published.id))
    assert r.errors is None and r.data["datasetResources"] == [{"name": "p.csv"}]
    r = run(AnonymousUser(), ONE, id=str(world.pub_res.id))
    assert r.errors is None and r.data["resourceById"]["name"] == "p.csv"


@pytest.mark.parametrize("who", ["anonymous", "outsider"])
def test_draft_resources_are_hidden(world, who):
    user = AnonymousUser() if who == "anonymous" else world.users[who]
    r = run(user, LIST, ds=str(world.draft.id))
    assert r.errors is None and r.data["datasetResources"] == []
    r = run(user, ONE, id=str(world.draft_res.id))
    assert r.errors and "does not exist" in str(r.errors[0].message)


@pytest.mark.parametrize("who", ["owner", "editor", "viewer", "shared", "admin"])
def test_draft_resources_visible_to_people_who_can_see_the_draft(world, who):
    user = world.users[who]
    r = run(user, LIST, ds=str(world.draft.id))
    assert r.errors is None and r.data["datasetResources"] == [{"name": "d.csv"}]
    r = run(user, ONE, id=str(world.draft_res.id))
    assert r.errors is None and r.data["resourceById"]["name"] == "d.csv"


def test_all_resources_list_hides_drafts(world):
    query = "{ resources { name } }"
    r = run(AnonymousUser(), query)
    assert r.errors is None and r.data["resources"] == [{"name": "p.csv"}]
    r = run(world.users["outsider"], query)
    assert r.data["resources"] == [{"name": "p.csv"}]
    r = run(world.users["owner"], query)
    assert sorted(x["name"] for x in r.data["resources"]) == ["d.csv", "p.csv"]
