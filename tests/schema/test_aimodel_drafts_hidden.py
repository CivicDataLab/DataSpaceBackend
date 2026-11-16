"""Draft AI models must not be visible to the public (#293).

Root cause: `getAiModel`, the anonymous `aiModels` list, `aiModelsTable(includePublic)`
and `getModelEndpoints` showed any model with `isPublic` set, whatever its status,
and the REST detail `GET /api/aimodels/<id>/` showed every model to everyone. The
dashboard sets `isPublic` when a draft's details are saved, so unpublished drafts
were readable by anyone with the link, while search (correctly) left them out.

Fix: one rule in `api/utils/aimodel_access.py`, the one search already uses. The
public sees a model only when it is public, active and ACTIVE/APPROVED; drafts are
seen by their owner, members of their organisation whose role can view, and
superusers.
"""

import types

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIClient

from api.models import AIModel, Organization
from api.schema.schema import schema
from api.utils.enums import AIModelStatus
from authorization.models import OrganizationMembership, Role, User


def run(user, query, **variables):
    ctx = types.SimpleNamespace(user=user, context={}, request=None, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", keycloak_id="owner")


@pytest.fixture
def stranger(db):
    return User.objects.create(username="stranger", keycloak_id="stranger")


def make_model(owner, **kw):
    data = dict(
        name="m",
        display_name="M",
        description="d",
        model_type="TRANSLATION",
        provider="OPENAI",
        user=owner,
        is_public=True,
    )
    data.update(kw)
    return AIModel.objects.create(**data)


@pytest.fixture
def draft(owner):
    # What the dashboard leaves behind after saving details: public flag set, never published.
    return make_model(owner, name="draft", status=AIModelStatus.REGISTERED)


@pytest.fixture
def published(owner):
    return make_model(owner, name="published", status=AIModelStatus.ACTIVE)


GET = "query($id: Int!){ getAiModel(modelId: $id){ id } }"


def visible(user, model):
    data = run(user, GET, id=model.id).data
    return data["getAiModel"] is not None


def test_public_draft_hidden_from_anonymous_and_strangers(draft, stranger):
    assert not visible(AnonymousUser(), draft)
    assert not visible(stranger, draft)


def test_published_model_visible_to_everyone(published, stranger):
    assert visible(AnonymousUser(), published)
    assert visible(stranger, published)


def test_owner_superuser_and_org_viewer_still_see_draft(owner, draft, db):
    org = Organization.objects.create(name="Org", description="o", slug="org")
    draft.organization = org
    draft.save()
    viewer = User.objects.create(username="viewer", keycloak_id="viewer")
    OrganizationMembership.objects.create(
        user=viewer, organization=org, role=Role.objects.create(name="viewer", can_view=True)
    )
    superuser = User.objects.create(username="su", keycloak_id="su", is_superuser=True)

    assert visible(owner, draft)
    assert visible(viewer, draft)
    assert visible(superuser, draft)


def test_anonymous_list_and_table_show_only_published(draft, published):
    listed = run(AnonymousUser(), "{ aiModels { id } }").data["aiModels"]
    table = run(AnonymousUser(), "{ aiModelsTable(includePublic: true){ data { id } } }").data

    assert [int(m["id"]) for m in listed] == [published.id]
    assert [int(m["id"]) for m in table["aiModelsTable"]["data"]] == [published.id]


@pytest.fixture
def local_cache(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def test_rest_detail_hides_drafts_from_strangers(local_cache, draft, published, stranger):
    client = APIClient()
    assert client.get(f"/api/aimodels/{draft.id}/").status_code == 404
    assert client.get(f"/api/aimodels/{published.id}/").status_code == 200

    client.force_authenticate(stranger)
    assert client.get(f"/api/aimodels/{draft.id}/").status_code == 404


def test_rest_detail_cache_does_not_leak_owner_view(local_cache, owner, draft):
    owner_client = APIClient()
    owner_client.force_authenticate(owner)
    assert owner_client.get(f"/api/aimodels/{draft.id}/").status_code == 200

    # The owner's request filled the shared cache; an anonymous caller still gets 404.
    assert APIClient().get(f"/api/aimodels/{draft.id}/").status_code == 404
