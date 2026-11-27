"""Saved AI model credentials are only returned to people who can edit the model.

Root cause: `TypeVersionProvider` exposed `apiKey`, `apiHeaders`, `hfAuthToken` and
the free-form `config` (which may hold a secret), `TypeAIModel` exposed
`hfAuthToken` (via `fields="__all__"`) and `TypeModelEndpoint` exposed `headers` as
plain fields. Published models are public, so anyone, signed in or not, could read
the credentials saved on them.

Fix: those fields resolve through `can_read_model_secrets` in
`api/utils/aimodel_access.py`: the owner, members of the model's organisation whose
role can change, and superusers get the saved value; everyone else gets null (or an
empty object for the header fields and `config`, which keep their non-null type).
The dashboard's edit page still reads them back for editors.
"""

import types

import pytest
from django.contrib.auth.models import AnonymousUser

from api.models import AIModel, AIModelVersion, Organization, VersionProvider
from api.models.AIModel import ModelEndpoint
from api.schema.schema import schema
from api.utils.enums import AIModelStatus
from authorization.models import OrganizationMembership, Role, User

KEY = "sk-test-not-a-real-key"
HF = "hf_test_not_a_real_token"
HEADERS = {"X-Api-Key": "header-secret"}
CONFIG = {"name": "Main", "apiKeyLocation": "query", "token": "config-secret"}

QUERY = """
query($id: Int!) {
  getAiModel(modelId: $id) {
    hfAuthToken
    endpoints { headers }
    versions { providers { apiKey apiHeaders hfAuthToken config apiKeyPrefix } }
  }
}
"""


def run(user, query, **variables):
    ctx = types.SimpleNamespace(user=user, context={}, request=None, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org", description="o", slug="org")


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", keycloak_id="owner")


def member(org, name, **flags):
    user = User.objects.create(username=name, keycloak_id=name)
    role = Role.objects.create(name=name, **flags)
    OrganizationMembership.objects.create(user=user, organization=org, role=role)
    return user


@pytest.fixture
def users(db, org, owner):
    return {
        "owner": owner,
        "superuser": User.objects.create(username="su", keycloak_id="su", is_superuser=True),
        "editor": member(org, "editor", can_view=True, can_add=True, can_change=True),
        "viewer": member(org, "viewer", can_view=True),
        "outsider": User.objects.create(username="outsider", keycloak_id="outsider"),
        "anonymous": AnonymousUser(),
    }


@pytest.fixture
def model(owner, org):
    m = AIModel.objects.create(
        name="m",
        display_name="M",
        description="d",
        model_type="TRANSLATION",
        provider="OPENAI",
        user=owner,
        organization=org,
        is_public=True,
        is_active=True,
        status=AIModelStatus.ACTIVE,
        hf_auth_token=HF,
    )
    version = AIModelVersion.objects.create(ai_model=m, version="1.0")
    VersionProvider.objects.create(
        version=version,
        provider="OPENAI",
        api_key=KEY,
        api_key_prefix="Bearer",
        api_headers=HEADERS,
        hf_auth_token=HF,
        config=CONFIG,
    )
    ModelEndpoint.objects.create(model=m, url="https://example.org/v1", headers=HEADERS)
    return m


def read(user, model):
    result = run(user, QUERY, id=model.id)
    assert result.errors is None, result.errors
    data = result.data["getAiModel"]
    provider = data["versions"][0]["providers"][0]
    return data, provider


@pytest.mark.parametrize("who", ["owner", "superuser", "editor"])
def test_editors_get_saved_credentials(users, model, who):
    data, provider = read(users[who], model)

    assert data["hfAuthToken"] == HF
    assert data["endpoints"][0]["headers"] == HEADERS
    assert provider["apiKey"] == KEY
    assert provider["apiHeaders"] == HEADERS
    assert provider["hfAuthToken"] == HF
    assert provider["config"] == CONFIG


@pytest.mark.parametrize("who", ["viewer", "outsider", "anonymous"])
def test_others_see_the_published_model_without_credentials(users, model, who):
    data, provider = read(users[who], model)

    assert data["hfAuthToken"] is None
    assert data["endpoints"][0]["headers"] == {}
    assert provider["apiKey"] is None
    assert provider["apiHeaders"] == {}
    assert provider["hfAuthToken"] is None
    assert provider["config"] == {}
    # Non-secret settings are still there.
    assert provider["apiKeyPrefix"] == "Bearer"


def test_anonymous_list_has_no_credentials(model):
    query = "{ aiModels { hfAuthToken versions { providers { apiKey apiHeaders hfAuthToken } } } }"
    result = run(AnonymousUser(), query)

    assert result.errors is None, result.errors
    [listed] = result.data["aiModels"]
    assert listed["hfAuthToken"] is None
    assert listed["versions"][0]["providers"][0] == {
        "apiKey": None,
        "apiHeaders": {},
        "hfAuthToken": None,
    }


def test_individual_model_credentials_only_for_its_owner(owner, users):
    lone = AIModel.objects.create(
        name="lone",
        display_name="Lone",
        description="d",
        model_type="TRANSLATION",
        provider="OPENAI",
        user=owner,
        is_public=True,
        is_active=True,
        status=AIModelStatus.ACTIVE,
        hf_auth_token=HF,
    )

    assert run(owner, QUERY, id=lone.id).data["getAiModel"]["hfAuthToken"] == HF
    # The editor of some organisation has no rights on a model without one.
    assert run(users["editor"], QUERY, id=lone.id).data["getAiModel"]["hfAuthToken"] is None
