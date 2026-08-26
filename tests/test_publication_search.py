"""Search-layer tests for Publication.

Elasticsearch itself is disabled in the deterministic layers, so these verify
the index-decision logic and the related-model re-index mapping (which is what
prevents draft leakage and stale facets) rather than round-tripping a cluster.
The full query/filter/pagination behaviour is a Layer-4 scenario that runs
against a live index (documented in the arch doc).
"""

from datetime import date

import pytest

from api.models import Geography, Publication, ResourceType, Sector
from api.models.Organization import Organization
from api.signals.publication_signals import _should_be_indexed
from api.utils.enums import GeoTypes, PublicationStatus
from authorization.models import User
from search.documents import PublicationDocument
from search.documents.publication_document import PublicationDocument as DocClass


@pytest.fixture
def user(db):
    return User.objects.create(username="author", keycloak_id="author")


@pytest.fixture
def resource_type(db):
    return ResourceType.objects.create(name="Report")


def _publication(user, resource_type, status=PublicationStatus.PUBLISHED, **extra):
    return Publication.objects.create(
        title="Findings",
        description="d",
        user=user,
        resource_type=resource_type,
        publication_date=date(2024, 1, 1),
        status=status,
        **extra,
    )


@pytest.mark.django_db
class TestIndexDecision:
    def test_published_resource_is_indexed(self, user, resource_type):
        publication = _publication(user, resource_type, status=PublicationStatus.PUBLISHED)
        assert PublicationDocument().should_index_object(publication) is True

    def test_draft_resource_is_not_indexed(self, user, resource_type):
        publication = _publication(user, resource_type, status=PublicationStatus.DRAFT)
        assert PublicationDocument().should_index_object(publication) is False

    def test_signal_predicate_matches_published(self, user, resource_type):
        published = _publication(user, resource_type, status=PublicationStatus.PUBLISHED)
        draft = _publication(user, resource_type, status=PublicationStatus.DRAFT)
        assert _should_be_indexed(published) is True
        assert _should_be_indexed(draft) is False


@pytest.mark.django_db
class TestReindexMapping:
    def test_related_models_include_resource_type(self):
        # A renamed Resource Type must re-index affected publications, so the
        # facet doesn't go stale — ResourceType must be a related model.
        assert ResourceType in DocClass.Django.related_models

    def test_renaming_a_resource_type_finds_affected_publications(self, user, resource_type):
        publication = _publication(user, resource_type)

        affected = PublicationDocument().get_instances_from_related(resource_type)

        assert list(affected) == [publication]

    def test_changing_a_sector_finds_affected_publications(self, user, resource_type):
        sector = Sector.objects.create(name="Health")
        publication = _publication(user, resource_type)
        publication.sectors.add(sector)

        affected = PublicationDocument().get_instances_from_related(sector)

        assert list(affected) == [publication]

    def test_changing_a_geography_finds_affected_publications(self, user, resource_type):
        geography = Geography.objects.create(name="India", code="IN", type=GeoTypes.COUNTRY)
        publication = _publication(user, resource_type)
        publication.geographies.add(geography)

        affected = PublicationDocument().get_instances_from_related(geography)

        assert list(affected) == [publication]

    def test_org_owned_publication_reindexes_on_org_change(self, resource_type):
        org = Organization.objects.create(name="Org", description="o", slug="org")
        owner = User.objects.create(username="member", keycloak_id="member")
        publication = _publication(owner, resource_type, organization=org)

        affected = PublicationDocument().get_instances_from_related(org)

        assert list(affected) == [publication]
