"""Organization names whose slug is taken: a clear message, not a database error (#288).

Root cause: `Organization.save` makes the slug from the name on every save and the
slug column is unique, but neither `createOrganization` nor `updateOrganization`
checked it. Renaming an organization to "CivicDataLab" while another one had the
slug `civicdatalab` reached the client as Postgres' own text: duplicate key value
violates unique constraint "api_organization_slug_key". The same happened for a
name with no letters or digits (empty slug, taken by the first such name) and,
on Postgres, for a name whose slug is longer than the 75-character column.

Fix: `organization_name_error` in `api/models/Organization.py` is checked before
saving and returns a fixed message; an IntegrityError from a request that took the
slug in between gets the same message. `organization_slug` cuts slugs to 75.
"""

import types

import pytest
from django.test import RequestFactory

from api.models import Organization
from api.models.Organization import NAME_TAKEN, NAME_WITHOUT_LETTERS
from api.schema.schema import schema
from authorization.models import OrganizationMembership, Role, User

ORG = "... on TypeOrganization { id name slug } ... on OperationInfo { messages { message } }"
CREATE = f"mutation ($i: OrganizationInput!) {{ createOrganization(input: $i) {{ {ORG} }} }}"
UPDATE = f"mutation ($i: OrganizationInputPartial!) {{ updateOrganization(input: $i) {{ {ORG} }} }}"


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


def error(result):
    assert result.errors, f"expected an error, got {result.data}"
    return result.errors[0].message


def new_org(name):
    return {"name": name, "description": "d", "organizationTypes": "STATE_GOVERNMENT"}


@pytest.fixture
def world(db):
    Role.objects.create(name="admin", can_view=True, can_add=True, can_change=True, can_delete=True)
    admin = User.objects.create(username="admin", keycloak_id="admin", is_superuser=True)
    return types.SimpleNamespace(
        admin=admin,
        civic=Organization.objects.create(name="CivicDataLab", description="c"),
        test=Organization.objects.create(name="Test org", description="t"),
    )


@pytest.mark.parametrize(
    "name", ["CivicDataLab", "civicdatalab", "CivicDataLab!", " civicdatalab "]
)
def test_rename_to_a_taken_slug_is_refused(world, name):
    result = run(world.admin, UPDATE, i={"id": str(world.test.id), "name": name})

    assert error(result) == NAME_TAKEN
    world.test.refresh_from_db()
    assert (world.test.name, world.test.slug) == ("Test org", "test-org")


@pytest.mark.parametrize("name", ["CivicDataLab", "Civic.Data.Lab"])
def test_create_with_a_taken_slug_is_refused(world, name):
    result = run(world.admin, CREATE, i=new_org(name))

    assert error(result) == NAME_TAKEN
    assert Organization.objects.filter(slug="civicdatalab").count() == 1
    assert not OrganizationMembership.objects.exists()


def test_message_has_no_database_text(world):
    message = error(run(world.admin, UPDATE, i={"id": str(world.test.id), "name": "CivicDataLab"}))

    assert "duplicate" not in message and "constraint" not in message


@pytest.mark.parametrize("name", ["TEST ORG", "Test org", "test-org"])
def test_an_organization_keeps_its_own_slug(world, name):
    result = run(
        world.admin, UPDATE, i={"id": str(world.test.id), "name": name, "description": "new"}
    )

    assert not result.errors, result.errors
    assert result.data["updateOrganization"]["slug"] == "test-org"


def test_saving_other_fields_does_not_check_the_name(world):
    result = run(world.admin, UPDATE, i={"id": str(world.test.id), "description": "only this"})

    assert not result.errors, result.errors
    world.test.refresh_from_db()
    assert world.test.description == "only this"


def test_a_free_name_still_renames_and_moves_the_slug(world):
    result = run(world.admin, UPDATE, i={"id": str(world.test.id), "name": "Open Budgets"})

    assert not result.errors, result.errors
    assert result.data["updateOrganization"]["slug"] == "open-budgets"


@pytest.mark.parametrize("name", ["!!!", "   ", "संस्था", ""])
def test_a_name_without_letters_or_digits_is_refused(world, name):
    created = run(world.admin, CREATE, i=new_org(name))
    renamed = run(world.admin, UPDATE, i={"id": str(world.test.id), "name": name})

    assert error(created) == NAME_WITHOUT_LETTERS
    assert error(renamed) == NAME_WITHOUT_LETTERS
    assert Organization.objects.count() == 2


def test_create_still_works_and_makes_the_caller_admin(world):
    result = run(world.admin, CREATE, i=new_org("New Org"))

    assert not result.errors, result.errors
    org = Organization.objects.get(id=result.data["createOrganization"]["id"])
    assert org.slug == "new-org"
    assert OrganizationMembership.objects.filter(user=world.admin, organization=org).exists()


def test_a_long_name_gets_a_slug_that_fits_the_column(world):
    name = "Department of " + "Water Resources " * 12
    result = run(world.admin, CREATE, i=new_org(name.strip()))

    assert not result.errors, result.errors
    slug = result.data["createOrganization"]["slug"]
    assert len(slug) <= 75 and not slug.endswith("-")


def test_a_slug_taken_between_check_and_save_gets_the_same_message(world, monkeypatch):
    """Two requests with the same name: the second one's save hits the unique slug."""
    import api.schema.organization_schema as org_schema

    answers = iter([None, NAME_TAKEN])
    monkeypatch.setattr(org_schema, "organization_name_error", lambda *a: next(answers))

    renamed = run(world.admin, UPDATE, i={"id": str(world.test.id), "name": "CivicDataLab"})
    assert error(renamed) == NAME_TAKEN
    world.test.refresh_from_db()
    assert world.test.slug == "test-org"

    answers = iter([None, NAME_TAKEN])
    created = run(world.admin, CREATE, i=new_org("CivicDataLab"))
    assert error(created) == NAME_TAKEN
    assert Organization.objects.count() == 2
    assert not OrganizationMembership.objects.exists()
