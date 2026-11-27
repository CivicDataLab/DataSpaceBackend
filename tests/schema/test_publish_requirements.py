"""Use cases, collaboratives and datasets published while still empty (#292).

Root cause: `publishUseCase`, `publishCollaborative` and `publishDataset` only
flipped the status (the dataset one had `# TODO: validate dataset`). The
frontend's publish step blocks an incomplete draft, but a direct API call
published it anyway.

Fix: api/services/publish_requirements.py holds the frontend's rules; each
publish mutation calls it first and refuses with one message naming every
missing part, as a GraphQL error (the frontend's publish calls would read a
refusal returned as data as success). The draft stays a draft.
"""

import json
import types

import pytest
from django.test import RequestFactory

from api.models import SDG, Collaborative, Dataset, Resource, Sector, Tag, UseCase
from api.schema.schema import schema
from api.utils.enums import CollaborativeStatus, DatasetStatus, UseCaseStatus
from authorization.models import User

PUBLISH_USE_CASE = """mutation($i: String!){ publishUseCase(useCaseId:$i){
  ... on TypeUseCase { status } ... on OperationInfo { messages { message } } } }"""
PUBLISH_COLLAB = """mutation($i: String!){ publishCollaborative(collaborativeId:$i){
  ... on TypeCollaborative { status } ... on OperationInfo { messages { message } } } }"""
PUBLISH_DATASET = """mutation($i: UUID!){ publishDataset(datasetId:$i){
  ... on TypeDataset { status } ... on OperationInfo { messages { message } } } }"""


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


def answer(result, field):
    assert result.errors is None, result.errors
    return result.data[field]


def refusal(result, field):
    assert result.data is None or result.data[field] is None, result.data
    assert len(result.errors) == 1, result.errors
    return result.errors[0].message


def blocks(*items):
    return json.dumps({"version": 1, "subtitle": "", "blocks": list(items)})


TEXT_BLOCK = {"id": "1", "type": "text", "html": "<p>What we built</p>"}


@pytest.fixture
def admin(db):
    return User.objects.create(
        username="admin", email="a@example.org", keycloak_id="admin", is_superuser=True
    )


@pytest.fixture
def sector(db):
    return Sector.objects.create(name="Health", slug="health")


@pytest.fixture
def sdg(db):
    return SDG.objects.create(name="Good health", code="SDG3", slug="sdg3")


@pytest.fixture
def dataset(admin, sector):
    dataset = Dataset.objects.create(title="Clinics", description="Clinic list", user=admin)
    dataset.sectors.add(sector)
    dataset.tags.add(Tag.objects.create(value="clinics"))
    Resource.objects.create(name="clinics.csv", dataset=dataset)
    return dataset


# ─── Use case ─────────────────────────────────────────────────────────────────


@pytest.fixture
def ready_use_case(admin, sector, sdg, dataset):
    use_case = UseCase.objects.create(title="Clinic finder", summary=blocks(TEXT_BLOCK), user=admin)
    UseCase.objects.filter(pk=use_case.pk).update(logo="logos/clinic.png")
    use_case.refresh_from_db()
    use_case.sectors.add(sector)
    use_case.sdgs.add(sdg)
    use_case.datasets.add(dataset)
    return use_case


def test_complete_use_case_publishes(admin, ready_use_case):
    result = run(admin, PUBLISH_USE_CASE, i=str(ready_use_case.id))

    assert answer(result, "publishUseCase")["status"] == UseCaseStatus.PUBLISHED


def test_empty_use_case_is_refused_and_names_everything_missing(admin):
    use_case = UseCase.objects.create(title="New use_case", user=admin)

    message = refusal(run(admin, PUBLISH_USE_CASE, i=str(use_case.id)), "publishUseCase")

    assert message == (
        "Cannot publish yet: upload a thumbnail image; add at least one content block; "
        "select at least one sector; select at least one SDG; connect at least one dataset."
    )
    use_case.refresh_from_db()
    assert use_case.status == UseCaseStatus.DRAFT


@pytest.mark.parametrize(
    "summary",
    [
        blocks(),
        blocks({"id": "1", "type": "text", "html": "<p>&nbsp;</p>"}),
        blocks({"id": "1", "type": "link", "url": "  "}),
        "<p> </p>",
    ],
    ids=["no-blocks", "empty-text", "empty-link", "empty-html"],
)
def test_use_case_without_content_is_refused(admin, ready_use_case, summary):
    UseCase.objects.filter(pk=ready_use_case.pk).update(summary=summary)

    message = refusal(run(admin, PUBLISH_USE_CASE, i=str(ready_use_case.id)), "publishUseCase")

    assert message == "Cannot publish yet: add at least one content block."


@pytest.mark.parametrize(
    "summary",
    [
        blocks({"id": "1", "type": "chart", "chartId": "abc"}),
        blocks({"id": "1", "type": "highlight", "title": "Result", "body": ""}),
        "<p>An older draft written as HTML</p>",
    ],
    ids=["chart", "highlight", "legacy-html"],
)
def test_use_case_content_in_other_forms_counts(admin, ready_use_case, summary):
    UseCase.objects.filter(pk=ready_use_case.pk).update(summary=summary)

    result = run(admin, PUBLISH_USE_CASE, i=str(ready_use_case.id))

    assert answer(result, "publishUseCase")["status"] == UseCaseStatus.PUBLISHED


# ─── Collaborative ────────────────────────────────────────────────────────────


@pytest.fixture
def ready_collaborative(admin, sector, sdg, dataset):
    collaborative = Collaborative.objects.create(
        title="Health data", summary="<p>Shared clinic data</p>", user=admin
    )
    collaborative.sectors.add(sector)
    collaborative.sdgs.add(sdg)
    collaborative.datasets.add(dataset)
    return collaborative


def test_complete_collaborative_publishes(admin, ready_collaborative):
    result = run(admin, PUBLISH_COLLAB, i=str(ready_collaborative.id))

    assert answer(result, "publishCollaborative")["status"] == CollaborativeStatus.PUBLISHED


def test_collaborative_with_a_use_case_instead_of_a_dataset_publishes(
    admin, ready_collaborative, ready_use_case
):
    ready_collaborative.datasets.clear()
    ready_collaborative.use_cases.add(ready_use_case)

    result = run(admin, PUBLISH_COLLAB, i=str(ready_collaborative.id))

    assert answer(result, "publishCollaborative")["status"] == CollaborativeStatus.PUBLISHED


def test_empty_collaborative_is_refused_and_names_everything_missing(admin):
    collaborative = Collaborative.objects.create(title="New collaborative", user=admin)

    message = refusal(run(admin, PUBLISH_COLLAB, i=str(collaborative.id)), "publishCollaborative")

    assert message == (
        "Cannot publish yet: add a description; select at least one sector; "
        "select at least one SDG; connect at least one dataset or use case."
    )
    collaborative.refresh_from_db()
    assert collaborative.status == CollaborativeStatus.DRAFT


def test_collaborative_description_of_only_markup_is_refused(admin, ready_collaborative):
    Collaborative.objects.filter(pk=ready_collaborative.pk).update(summary="<p>&nbsp;</p>")

    message = refusal(
        run(admin, PUBLISH_COLLAB, i=str(ready_collaborative.id)), "publishCollaborative"
    )

    assert message == "Cannot publish yet: add a description."


# ─── Dataset ──────────────────────────────────────────────────────────────────


def test_complete_dataset_publishes(admin, dataset):
    result = run(admin, PUBLISH_DATASET, i=str(dataset.id))

    assert answer(result, "publishDataset")["status"] == DatasetStatus.PUBLISHED


def test_empty_dataset_is_refused_and_names_everything_missing(admin):
    dataset = Dataset.objects.create(title="New dataset", user=admin)

    message = refusal(run(admin, PUBLISH_DATASET, i=str(dataset.id)), "publishDataset")

    assert message == (
        "Cannot publish yet: add at least one resource; add a description; "
        "select at least one sector; add at least one tag."
    )
    dataset.refresh_from_db()
    assert dataset.status == DatasetStatus.DRAFT


def test_dataset_without_resources_is_refused(admin, dataset):
    dataset.resources.all().delete()

    message = refusal(run(admin, PUBLISH_DATASET, i=str(dataset.id)), "publishDataset")

    assert message == "Cannot publish yet: add at least one resource."
