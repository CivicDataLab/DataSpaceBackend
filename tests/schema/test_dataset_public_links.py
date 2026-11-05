import types

import pytest
from django.contrib.auth.models import AnonymousUser

from api.models import Dataset
from api.schema.schema import schema
from api.services.metadata_export.adapter import dataset_to_record
from api.utils.enums import DatasetStatus
from authorization.models import User

QUERY = """
query($id: UUID, $pid: String) {
  getDataset(datasetId: $id, publicId: $pid) { id title publicId urlSlug }
}
"""


def run(query, user, variables):
    ctx = types.SimpleNamespace(user=user, context={})
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def published(db):
    return Dataset.objects.create(title="City Air Quality Index", status=DatasetStatus.PUBLISHED)


@pytest.fixture
def draft(db):
    return Dataset.objects.create(title="Secret draft", status=DatasetStatus.DRAFT)


def test_new_dataset_gets_public_id_and_link(published) -> None:
    assert len(published.public_id) == 12
    assert published.url_slug == f"city-air-quality-index-{published.public_id}"


def test_rename_keeps_public_id(published) -> None:
    old = published.public_id
    published.title = "Air Quality Index for Cities"
    published.save()
    published.refresh_from_db()
    assert published.public_id == old
    assert published.url_slug == f"air-quality-index-for-cities-{old}"


def test_get_by_public_id_anonymous(published) -> None:
    for value in [published.public_id, published.url_slug, f"old-words-{published.public_id}"]:
        res = run(QUERY, AnonymousUser(), {"pid": value})
        assert res.errors is None, res.errors
        assert res.data["getDataset"]["id"] == str(published.id)
        assert res.data["getDataset"]["urlSlug"] == published.url_slug


def test_get_by_uuid_still_works(published) -> None:
    res = run(QUERY, AnonymousUser(), {"id": str(published.id)})
    assert res.errors is None, res.errors
    assert res.data["getDataset"]["publicId"] == published.public_id


def test_unknown_or_bad_public_id_gives_null(published) -> None:
    user = User.objects.create(username="u1", keycloak_id="u1")
    for value in ["aaaaaaaaaaaa", "not-a-link", str(published.id)]:
        res = run(QUERY, user, {"pid": value})
        assert res.errors is None, res.errors
        assert res.data["getDataset"] is None


def test_draft_by_public_id_needs_login(draft) -> None:
    res = run(QUERY, AnonymousUser(), {"pid": draft.public_id})
    assert res.errors
    assert res.data is None or res.data["getDataset"] is None


def test_draft_by_public_id_other_user_denied(draft) -> None:
    stranger = User.objects.create(username="u2", keycloak_id="u2")
    res = run(QUERY, stranger, {"pid": draft.public_id})
    assert res.errors


def test_draft_by_public_id_superuser(draft) -> None:
    admin = User.objects.create(username="admin", keycloak_id="admin", is_superuser=True)
    res = run(QUERY, admin, {"pid": draft.public_id})
    assert res.errors is None, res.errors
    assert res.data["getDataset"]["publicId"] == draft.public_id


def test_export_landing_link_uses_url_slug(published) -> None:
    record = dataset_to_record(published)
    assert record["landing_page"].endswith(f"/datasets/{published.url_slug}")


def test_hindi_title_link_is_just_the_id(db) -> None:
    ds = Dataset.objects.create(title="जनगणना डेटा", status=DatasetStatus.PUBLISHED)
    assert ds.url_slug == ds.public_id
    res = run(QUERY, AnonymousUser(), {"pid": ds.url_slug})
    assert res.data["getDataset"]["id"] == str(ds.id)
