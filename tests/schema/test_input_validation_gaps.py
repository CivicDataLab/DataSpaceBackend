"""Mutation input the API accepted without checking (#292).

Root cause: mutations set fields and call save() without full_clean, so model
rules (URLField, choices, column lengths) never ran, and some rules were never
written at all (date order, positive numbers). Postgres caught over-long titles
with its own error text. A refused upload was validated after its Resource row
was created, so the row stayed behind. Prompt metadata saved `purpose` but
`promptMetadata` never returned it.

Fix: the checks in api/utils/input_checks.py, called by each resolver before it
saves; uploads create and validate inside one transaction and remove the stored
file when refused; `promptMetadata` returns `purpose`.
"""

import datetime
import types

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from api.models import (
    AIModel,
    AIModelVersion,
    Collaborative,
    Dataset,
    PromptDataset,
    Resource,
    UseCase,
    VersionProvider,
)
from api.schema.schema import schema
from api.utils.enums import DatasetStatus
from authorization.models import User


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


def refused(result, field):
    """True when the mutation answered with an error instead of saving."""
    if result.errors:
        return True
    payload = result.data[field]
    return isinstance(payload, dict) and payload.get("success") is False


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", email="o@example.org", keycloak_id="owner")


# ─── Use cases and collaboratives ─────────────────────────────────────────────

UPDATE_USE_CASE = "mutation($d: UseCaseInputPartial!){ updateUseCase(data:$d){ id } }"
UPDATE_COLLAB = "mutation($d: CollaborativeInputPartial!){ updateCollaborative(data:$d){ id } }"


@pytest.fixture
def use_case(owner):
    return UseCase.objects.create(title="Use case", user=owner)


@pytest.fixture
def collaborative(owner):
    return Collaborative.objects.create(title="Collab", user=owner)


@pytest.mark.parametrize("url", ["not a url", "javascript:alert(1)"])
def test_use_case_invalid_platform_url_is_refused(owner, use_case, url):
    result = run(owner, UPDATE_USE_CASE, d={"id": str(use_case.id), "platformUrl": url})

    assert refused(result, "updateUseCase")
    use_case.refresh_from_db()
    assert use_case.platform_url is None


def test_use_case_valid_platform_url_is_saved(owner, use_case):
    result = run(
        owner, UPDATE_USE_CASE, d={"id": str(use_case.id), "platformUrl": "https://example.org"}
    )

    assert result.errors is None
    use_case.refresh_from_db()
    assert use_case.platform_url == "https://example.org"


@pytest.mark.parametrize(
    "query,instance,field",
    [
        (UPDATE_USE_CASE, "use_case", "updateUseCase"),
        (UPDATE_COLLAB, "collaborative", "updateCollaborative"),
    ],
)
def test_completed_before_started_is_refused(owner, request, query, instance, field):
    obj = request.getfixturevalue(instance)
    dates = {"startedOn": "2025-06-01", "completedOn": "2024-01-01"}

    assert refused(run(owner, query, d={"id": str(obj.id), **dates}), field)


def test_completed_date_alone_is_checked_against_stored_start(owner, use_case):
    use_case.started_on = datetime.date(2025, 6, 1)
    use_case.save()

    result = run(owner, UPDATE_USE_CASE, d={"id": str(use_case.id), "completedOn": "2024-01-01"})

    assert refused(result, "updateUseCase")
    assert (
        run(owner, UPDATE_USE_CASE, d={"id": str(use_case.id), "completedOn": "2025-06-01"}).errors
        is None
    )


# ─── AI models ────────────────────────────────────────────────────────────────


@pytest.fixture
def model(owner):
    return AIModel.objects.create(
        name="m", display_name="M", model_type="TRANSLATION", provider="OPENAI", user=owner
    )


@pytest.fixture
def provider(model):
    version = AIModelVersion.objects.create(ai_model=model, version="1.0")
    return VersionProvider.objects.create(version=version, provider="OPENAI")


UPDATE_MODEL = "mutation($i: UpdateAIModelInput!){ updateAiModel(input:$i){ success } }"
UPDATE_PROVIDER = (
    "mutation($i: UpdateVersionProviderInput!){ updateVersionProvider(input:$i){ success } }"
)


@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_max_tokens_is_refused(owner, model, value):
    result = run(owner, UPDATE_MODEL, i={"id": model.id, "maxTokens": value})

    assert refused(result, "updateAiModel")
    model.refresh_from_db()
    assert model.max_tokens != value


@pytest.mark.parametrize("url", ["not a url", "javascript:alert(1)", "ftp://example.org/x"])
def test_invalid_endpoint_url_is_refused(owner, provider, url):
    assert refused(
        run(owner, UPDATE_PROVIDER, i={"id": provider.id, "apiEndpointUrl": url}),
        "updateVersionProvider",
    )


@pytest.mark.parametrize("value", [0, -5, 601, 100000])
def test_timeout_outside_1_to_600_is_refused(owner, provider, value):
    result = run(owner, UPDATE_PROVIDER, i={"id": provider.id, "apiTimeoutSeconds": value})

    assert refused(result, "updateVersionProvider")
    provider.refresh_from_db()
    assert provider.api_timeout_seconds != value


def test_valid_provider_settings_are_saved(owner, provider, monkeypatch):
    # The host must resolve to a public address; answer for it without the network.
    public = [(2, 1, 6, "", ("93.184.215.14", 443))]
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: public)
    result = run(
        owner,
        UPDATE_PROVIDER,
        i={
            "id": provider.id,
            "apiEndpointUrl": "https://api.example.org/v1",
            "apiTimeoutSeconds": 600,
        },
    )

    assert result.data["updateVersionProvider"]["success"], result
    provider.refresh_from_db()
    assert (provider.api_endpoint_url, provider.api_timeout_seconds) == (
        "https://api.example.org/v1",
        600,
    )


# ─── Prompt datasets ──────────────────────────────────────────────────────────

META = "mutation($i: UpdatePromptMetadataInput!){ updatePromptMetadata(updateInput:$i){ success } }"
PROMPT_RES = (
    "mutation($i: UpdatePromptResourceInput!){ updatePromptResource(updateInput:$i){ success } }"
)
READ = "query($f: DatasetFilter){ datasets(filters:$f){ promptMetadata } }"


@pytest.fixture
def prompt_dataset(owner):
    return PromptDataset.objects.create(title="Prompts", user=owner, status=DatasetStatus.DRAFT)


@pytest.fixture
def prompt_resource(prompt_dataset):
    return Resource.objects.create(name="p.csv", dataset=prompt_dataset)


def test_unknown_domain_is_refused(owner, prompt_dataset):
    result = run(owner, META, i={"dataset": str(prompt_dataset.id), "domain": "NOT_A_DOMAIN"})

    assert result.errors is None and result.data["updatePromptMetadata"]["success"] is False
    prompt_dataset.refresh_from_db()
    assert prompt_dataset.domain is None


def test_purpose_is_returned(owner, prompt_dataset):
    run(owner, META, i={"dataset": str(prompt_dataset.id), "purpose": "EVALUATION"})

    data = run(owner, READ, f={"id": str(prompt_dataset.id)}).data
    assert data["datasets"][0]["promptMetadata"]["purpose"] == "EVALUATION"


@pytest.mark.parametrize(
    "fields",
    [{"promptFormat": "NOT_A_FORMAT"}, {"promptCount": -1}, {"avgPromptLength": -5}],
    ids=["format", "count", "avg-length"],
)
def test_bad_prompt_resource_values_are_refused(owner, prompt_resource, fields):
    result = run(owner, PROMPT_RES, i={"resource": str(prompt_resource.id), **fields})

    assert result.errors is None and result.data["updatePromptResource"]["success"] is False


def test_valid_prompt_resource_values_are_saved(owner, prompt_resource):
    fields = {"promptFormat": "CHAT", "promptCount": 0, "avgPromptLength": 42}

    result = run(owner, PROMPT_RES, i={"resource": str(prompt_resource.id), **fields})

    assert result.data["updatePromptResource"]["success"], result


# ─── Datasets ─────────────────────────────────────────────────────────────────

UPDATE_DATASET = """mutation($i: UpdateDatasetInput!){
  updateDataset(updateDatasetInput:$i){ ... on TypeDataset { id } }
}"""
UPLOAD = """mutation($ds: UUID!, $file: Upload!){
  createFileResources(fileResourceInput:{dataset:$ds, files:[$file]}){ id }
}"""


@pytest.fixture
def dataset(owner):
    return Dataset.objects.create(title="Original", user=owner, status=DatasetStatus.DRAFT)


@pytest.mark.parametrize("field,limit", [("title", 300), ("description", 1000)])
def test_over_long_dataset_text_gets_a_field_message(owner, dataset, field, limit):
    result = run(owner, UPDATE_DATASET, i={"dataset": str(dataset.id), field: "x" * (limit + 1)})

    assert [e.message for e in result.errors or []] == [
        f"{field.capitalize()} cannot be longer than {limit} characters."
    ]
    dataset.refresh_from_db()
    assert dataset.title == "Original"


def test_refused_upload_leaves_no_resource(owner, dataset):
    exe = SimpleUploadedFile("tool.exe", b"MZ\x90\x00" + b"\x00" * 200)

    result = run(owner, UPLOAD, ds=str(dataset.id), file=exe)

    assert any("Unsupported file format" in e.message for e in result.errors or [])
    assert not Resource.objects.filter(dataset=dataset).exists()
