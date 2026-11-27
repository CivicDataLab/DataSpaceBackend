"""Updates must leave fields alone when the request leaves them out (#291).

Root cause: `UpdateDatasetInput`, `UpdateMetadataInput` and `UseCaseInputPartial`
gave `license`, `accessType` and `runningStatus` non-null defaults, so a request
that omitted them arrived with the default and the resolver wrote it. A
RESTRICTED dataset silently became PUBLIC. Separately, `updateDataset` saved the
title before the tags, so a tag too long for the tag table failed the request
after the title was already stored.

Fix: the inputs default to None, and both dataset updates check tags first and
write inside one transaction.
"""

import types

import pytest

from api.models import Dataset, Metadata, UseCase
from api.schema.schema import schema
from api.utils.enums import DatasetAccessType, DatasetStatus, UseCaseRunningStatus
from authorization.models import User

LICENSE = "CC0_1_0"


def run(user, query, **variables):
    ctx = types.SimpleNamespace(user=user, context={}, request=None, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", email="o@example.org", keycloak_id="owner")


@pytest.fixture
def dataset(owner):
    return Dataset.objects.create(
        title="Original title",
        description="d",
        user=owner,
        status=DatasetStatus.DRAFT,
        license=LICENSE,
        access_type=DatasetAccessType.RESTRICTED,
    )


UPDATE_DATASET = """
mutation($i: UpdateDatasetInput!) {
  updateDataset(updateDatasetInput: $i) { ... on TypeDataset { id } }
}
"""

UPDATE_METADATA = """
mutation($i: UpdateMetadataInput!) {
  addUpdateDatasetMetadata(updateMetadataInput: $i) { success errors { nonFieldErrors } }
}
"""


def test_update_dataset_without_license_keeps_license_and_access_type(owner, dataset):
    result = run(owner, UPDATE_DATASET, i={"dataset": str(dataset.id), "description": "x"})

    assert result.errors is None
    dataset.refresh_from_db()
    assert (dataset.description, dataset.license, dataset.access_type) == (
        "x",
        LICENSE,
        DatasetAccessType.RESTRICTED,
    )


def test_update_metadata_without_license_keeps_license_and_access_type(owner, dataset):
    result = run(
        owner, UPDATE_METADATA, i={"dataset": str(dataset.id), "metadata": [], "description": "y"}
    )

    assert result.errors is None
    dataset.refresh_from_db()
    assert (dataset.description, dataset.license, dataset.access_type) == (
        "y",
        LICENSE,
        DatasetAccessType.RESTRICTED,
    )


def test_update_dataset_still_sets_license_when_sent(owner, dataset):
    run(owner, UPDATE_DATASET, i={"dataset": str(dataset.id), "license": "CC_BY_4_0_ATTRIBUTION"})

    dataset.refresh_from_db()
    assert dataset.license == "CC_BY_4_0_ATTRIBUTION"


def test_too_long_tag_does_not_half_save(owner, dataset):
    result = run(
        owner,
        UPDATE_DATASET,
        i={"dataset": str(dataset.id), "title": "New title", "tags": ["x" * 51]},
    )

    assert result.errors and "Tags cannot exceed 50 characters." in result.errors[0].message
    dataset.refresh_from_db()
    assert dataset.title == "Original title"
    assert not dataset.tags.exists()


def test_bad_metadata_item_does_not_half_save(owner, dataset):
    disabled = Metadata.objects.create(
        label="Off",
        data_standard="",
        urn="ds:off",
        data_type="STRING",
        model="DATASET",
        enabled=False,
        filterable=False,
    )
    run(
        owner,
        UPDATE_METADATA,
        i={
            "dataset": str(dataset.id),
            "description": "should not stick",
            "metadata": [{"id": str(disabled.id), "value": "v"}],
        },
    )

    dataset.refresh_from_db()
    assert dataset.description == "d"


def test_update_use_case_without_running_status_keeps_it(owner):
    usecase = UseCase.objects.create(
        title="UC", user=owner, running_status=UseCaseRunningStatus.ON_HOLD
    )

    result = run(
        owner,
        "mutation($d: UseCaseInputPartial!){ updateUseCase(data: $d){ id } }",
        d={"id": str(usecase.id), "summary": "s"},
    )

    assert result.errors is None
    usecase.refresh_from_db()
    assert usecase.running_status == UseCaseRunningStatus.ON_HOLD
