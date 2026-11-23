"""AI model provider fields that go into the model call are saved without whitespace.

Root cause: `createVersionProvider` / `updateVersionProvider` saved the API key, Hugging
Face token, key prefix, auth header name, provider model ID and response path exactly as
sent. A space pasted unseen into the masked key field made every call to the model fail
with 401.

Fix: `_clean_provider_tokens` in `api/schema/aimodel_schema.py` trims the ends of these
fields and refuses whitespace left inside them (`whitespace_error` in
`api/utils/input_checks.py`), before anything is saved. With Custom Header or Basic auth
the key is a whole header value or `username:password`, so spaces inside it are kept.
"""

import types

import pytest
from django.test import RequestFactory

from api.models import AIModel, AIModelVersion, VersionProvider
from api.schema.schema import schema
from authorization.models import User

# GraphQL field -> (model field, a valid value)
FIELDS = {
    "apiKey": ("api_key", "sk-test-not-a-real-key"),
    "hfAuthToken": ("hf_auth_token", "hf_test_not_a_real_token"),
    "apiKeyPrefix": ("api_key_prefix", "Bearer"),
    "apiAuthHeaderName": ("api_auth_header_name", "X-Api-Key"),
    "providerModelId": ("provider_model_id", "gpt-4o-mini"),
    "apiResponsePath": ("api_response_path", "choices[0].message.content"),
}

UPDATE = """
mutation($i: UpdateVersionProviderInput!) {
  updateVersionProvider(input: $i) { success errors { nonFieldErrors } }
}
"""
CREATE = """
mutation($i: CreateVersionProviderInput!) {
  createVersionProvider(input: $i) { success errors { nonFieldErrors } }
}
"""


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", keycloak_id="owner")


@pytest.fixture
def version(owner):
    model = AIModel.objects.create(
        name="m", display_name="M", model_type="TRANSLATION", provider="OPENAI", user=owner
    )
    return AIModelVersion.objects.create(ai_model=model, version="1.0")


@pytest.fixture
def provider(version):
    return VersionProvider.objects.create(version=version, provider="OPENAI")


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("dirty", [" {} ", "{}\n", "\t{}\r\n"])
def test_whitespace_at_the_ends_is_trimmed(owner, provider, field, dirty):
    column, value = FIELDS[field]

    result = run(owner, UPDATE, i={"id": provider.id, field: dirty.format(value)})

    assert result.data["updateVersionProvider"]["success"] is True, result
    provider.refresh_from_db()
    assert getattr(provider, column) == value


@pytest.mark.parametrize("field", FIELDS)
def test_whitespace_inside_is_refused(owner, provider, field):
    column, value = FIELDS[field]
    before = getattr(provider, column)

    result = run(owner, UPDATE, i={"id": provider.id, field: f"{value[:3]} {value[3:]}"})

    payload = result.data["updateVersionProvider"]
    assert payload["success"] is False
    assert payload["errors"]["nonFieldErrors"][0].endswith("cannot contain spaces.")
    provider.refresh_from_db()
    assert getattr(provider, column) == before


def test_refused_update_changes_nothing_else(owner, provider):
    result = run(
        owner,
        UPDATE,
        i={"id": provider.id, "providerModelId": "new-model", "apiKey": "sk-a b"},
    )

    assert result.data["updateVersionProvider"]["success"] is False
    provider.refresh_from_db()
    assert provider.provider_model_id != "new-model"


def test_create_trims_the_api_key(owner, version):
    result = run(
        owner,
        CREATE,
        i={"versionId": version.id, "provider": "OPENAI", "apiKey": " sk-test-key\n"},
    )

    assert result.data["createVersionProvider"]["success"] is True, result
    assert VersionProvider.objects.get(version=version).api_key == "sk-test-key"


def test_create_refuses_a_key_with_a_space_inside(owner, version):
    result = run(
        owner,
        CREATE,
        i={"versionId": version.id, "provider": "OPENAI", "apiKey": "sk-test key"},
    )

    payload = result.data["createVersionProvider"]
    assert payload["success"] is False
    assert payload["errors"]["nonFieldErrors"] == ["API key cannot contain spaces."]
    assert not VersionProvider.objects.filter(version=version).exists()


def test_only_spaces_clears_the_key(owner, provider):
    VersionProvider.objects.filter(id=provider.id).update(api_key="sk-old")

    result = run(owner, UPDATE, i={"id": provider.id, "apiKey": "   "})

    assert result.data["updateVersionProvider"]["success"] is True
    provider.refresh_from_db()
    assert provider.api_key == ""


@pytest.mark.parametrize("auth", ["CUSTOM", "BASIC"])
def test_key_may_contain_spaces_for_custom_header_and_basic_auth(owner, provider, auth):
    result = run(
        owner, UPDATE, i={"id": provider.id, "apiAuthType": auth, "apiKey": " Token abc 1\n"}
    )

    assert result.data["updateVersionProvider"]["success"] is True, result
    provider.refresh_from_db()
    assert provider.api_key == "Token abc 1"


def test_saved_custom_auth_type_is_used_when_not_sent(owner, provider):
    VersionProvider.objects.filter(id=provider.id).update(api_auth_type="CUSTOM")

    result = run(owner, UPDATE, i={"id": provider.id, "apiKey": "Token abc"})

    assert result.data["updateVersionProvider"]["success"] is True
    provider.refresh_from_db()
    assert provider.api_key == "Token abc"


def test_switching_from_custom_to_bearer_checks_the_key(owner, provider):
    VersionProvider.objects.filter(id=provider.id).update(api_auth_type="CUSTOM")

    result = run(owner, UPDATE, i={"id": provider.id, "apiAuthType": "BEARER", "apiKey": "sk a"})

    assert result.data["updateVersionProvider"]["success"] is False


def test_create_with_custom_header_keeps_spaces_in_the_key(owner, version):
    result = run(
        owner,
        CREATE,
        i={
            "versionId": version.id,
            "provider": "CUSTOM",
            "apiAuthType": "CUSTOM",
            "apiKey": "Token abc",
        },
    )

    assert result.data["createVersionProvider"]["success"] is True, result
    assert VersionProvider.objects.get(version=version).api_key == "Token abc"
