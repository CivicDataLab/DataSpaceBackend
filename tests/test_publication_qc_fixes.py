"""Regression tests for the QC findings on the Resources backend.

B1 — linked-project fields are owner-gated and published-only (no draft-title leak).
B4 — the listing runs a bounded query count (no N+1).
O1 — an explicit-empty required field is rejected on update.
O2 — the plain use-case update mutation cannot attach a resource.
"""

import types
from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser

from api.models import Collaborative, Publication, ResourceType, UseCase
from api.models.Organization import Organization
from api.schema.schema import schema
from api.utils.enums import PublicationStatus, UseCaseStatus
from authorization.models import OrganizationMembership, Role, User


@pytest.fixture(autouse=True)
def _no_activity(monkeypatch):
    monkeypatch.setattr("api.schema.base_mutation.record_activity", lambda *a, **k: None)


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", keycloak_id="owner")


@pytest.fixture
def resource_type(db):
    return ResourceType.objects.create(name="Report")


def _pub(owner, rt, status=PublicationStatus.PUBLISHED, org=None, title="Findings"):
    return Publication.objects.create(
        title=title,
        description="d",
        user=owner,
        resource_type=rt,
        publication_date=date(2024, 1, 1),
        status=status,
        organization=org,
    )


def ctx(user, organization=None):
    return types.SimpleNamespace(
        user=user, context={"organization": organization} if organization else {}
    )


def run(query, user, variables=None, organization=None):
    return schema.execute_sync(
        query, variable_values=variables or {}, context_value=ctx(user, organization)
    )


LINKS = """
query($id: UUID!) {
  getPublication(publicationId: $id) {
    id linkedUsecases { id title } linkedCount
  }
}
"""


@pytest.mark.django_db
class TestLinkedFieldsGate:
    def _linked_setup(self, owner, rt):
        pub = _pub(owner, rt, status=PublicationStatus.PUBLISHED)
        published_uc = UseCase.objects.create(title="Public UC", user=owner)
        published_uc.status = UseCaseStatus.PUBLISHED
        published_uc.save()
        draft_uc = UseCase.objects.create(title="Secret Draft UC", user=owner)
        published_uc.publications.add(pub)
        draft_uc.publications.add(pub)
        return pub

    def test_anonymous_sees_no_linked_projects(self, owner, resource_type):
        pub = self._linked_setup(owner, resource_type)

        result = run(LINKS, AnonymousUser(), {"id": str(pub.id)})

        assert result.errors is None
        data = result.data["getPublication"]
        assert data["linkedUsecases"] == []  # no draft title leaked
        assert data["linkedCount"] == 0

    def test_owner_sees_only_published_links(self, owner, resource_type):
        pub = self._linked_setup(owner, resource_type)

        result = run(LINKS, owner, {"id": str(pub.id)})

        data = result.data["getPublication"]
        titles = [uc["title"] for uc in data["linkedUsecases"]]
        assert titles == ["Public UC"]  # the draft UC is hidden even from the owner
        assert data["linkedCount"] == 1


@pytest.mark.django_db
class TestListingIsBounded:
    def test_listing_query_count_is_bounded(
        self, owner, resource_type, django_assert_max_num_queries
    ):
        for i in range(5):
            pub = _pub(owner, resource_type, title=f"Doc {i}")
            pub.sectors.set([])
            pub.blocks.create(
                position=0,
                block_type="YOUTUBE",
                youtube_url="https://youtu.be/dQw4w9WgXcQ",
                youtube_video_id="dQw4w9WgXcQ",
            )

        query = """
        query {
          publications(includePublic: true) {
            id title resourceType { name } sectors { id } geographies { id } blocks { id }
          }
        }
        """
        # Bounded: a constant number of queries regardless of the 5 rows + relations.
        with django_assert_max_num_queries(15):
            result = run(query, owner)
        assert result.errors is None
        assert len(result.data["publications"]) == 5


UPDATE = """
mutation($input: UpdatePublicationInput!) {
  updatePublication(input: $input) { success errors { fieldErrors { field } } }
}
"""


@pytest.mark.django_db
class TestUpdateEmptyRejected:
    def test_explicit_empty_title_is_rejected(self, owner, resource_type):
        pub = _pub(owner, resource_type, status=PublicationStatus.DRAFT)

        result = run(UPDATE, owner, {"input": {"id": str(pub.id), "title": "  "}})

        assert result.data["updatePublication"]["success"] is False
        pub.refresh_from_db()
        assert pub.title == "Findings"  # not blanked


@pytest.mark.django_db
class TestPlainUpdateCannotAttachPublication:
    def test_usecase_input_has_no_publications_field(self, owner, resource_type):
        pub = _pub(owner, resource_type, status=PublicationStatus.PUBLISHED)
        uc = UseCase.objects.create(title="UC", user=owner)

        # The UC update input excludes 'publications', so passing it is a schema
        # error — the only way to attach a resource is the guarded link trio.
        mutation = """
        mutation($input: UseCaseInputPartial!) {
          updateUseCase(useCaseInputPartial: $input) { __typename }
        }
        """
        result = run(
            mutation,
            owner,
            {"input": {"id": str(uc.id), "publications": [str(pub.id)]}},
        )

        assert result.errors is not None  # 'publications' is not a valid input field
        assert uc.publications.count() == 0
