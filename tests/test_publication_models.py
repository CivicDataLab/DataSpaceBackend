"""Layer 1 DB tests for the Publication data model foundation.

Covers slug dedupe, ownership, the ResourceType lookup, the file-XOR-youtube
block constraint, block ordering, delete cascade, and the seed command.
"""

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from api.models import Publication, PublicationBlock, ResourceType
from api.models.Organization import Organization
from api.utils.enums import PublicationBlockType, PublicationStatus
from authorization.models import User


@pytest.fixture
def user(db):
    return User.objects.create(username="alice", keycloak_id="kc-alice")


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org A", description="an org", slug="org-a")


@pytest.mark.django_db
class TestPublicationSlug:
    def test_two_same_title_publications_get_distinct_slugs(self, user):
        first = Publication.objects.create(title="Annual Report", user=user)
        second = Publication.objects.create(title="Annual Report", user=user)

        assert first.slug == "annual-report"
        assert second.slug == "annual-report-1"
        assert first.slug != second.slug

    def test_a_unicode_title_slugs_without_crashing(self, user):
        publication = Publication.objects.create(title="Report — Résumé 2024", user=user)

        assert publication.slug
        assert Publication.objects.filter(slug=publication.slug).count() == 1


@pytest.mark.django_db
class TestPublicationOwnership:
    def test_a_user_owned_publication_reports_individual(self, user):
        publication = Publication.objects.create(title="Solo work", user=user)

        assert publication.is_individual_publication is True

    def test_an_org_owned_publication_is_not_individual(self, org, user):
        publication = Publication.objects.create(title="Org work", organization=org, user=user)

        assert publication.is_individual_publication is False


@pytest.mark.django_db
class TestResourceType:
    def test_name_is_unique(self):
        ResourceType.objects.create(name="Report")
        with transaction.atomic(), pytest.raises(IntegrityError):
            ResourceType.objects.create(name="Report")

    def test_slugifies_the_name(self):
        resource_type = ResourceType.objects.create(name="Policy Brief")

        assert resource_type.slug == "policy-brief"

    def test_is_active_defaults_true(self):
        resource_type = ResourceType.objects.create(name="Report")

        assert resource_type.is_active is True

    def test_active_query_returns_only_active_types(self):
        ResourceType.objects.create(name="Report")
        ResourceType.objects.create(name="Retired", is_active=False)

        active = ResourceType.objects.filter(is_active=True)

        assert active.count() == 1
        assert active.first().name == "Report"


@pytest.mark.django_db
class TestPublicationBlock:
    def _publication(self, user):
        return Publication.objects.create(title="With blocks", user=user)

    def test_file_block_stores_file_fields(self, user):
        publication = self._publication(user)

        block = PublicationBlock.objects.create(
            publication=publication,
            position=0,
            block_type=PublicationBlockType.FILE,
            file="publications/report.pdf",
            file_name="report.pdf",
            file_format="pdf",
            file_size=1024,
        )

        assert block.file_name == "report.pdf"
        assert block.file_format == "pdf"
        assert block.youtube_url is None

    def test_youtube_block_stores_youtube_fields(self, user):
        publication = self._publication(user)

        block = PublicationBlock.objects.create(
            publication=publication,
            position=0,
            block_type=PublicationBlockType.YOUTUBE,
            youtube_url="https://youtu.be/dQw4w9WgXcQ",
            youtube_video_id="dQw4w9WgXcQ",
        )

        assert block.youtube_video_id == "dQw4w9WgXcQ"
        assert block.file == ""

    def test_a_block_with_both_file_and_youtube_is_rejected(self, user):
        publication = self._publication(user)

        with transaction.atomic(), pytest.raises(IntegrityError):
            PublicationBlock.objects.create(
                publication=publication,
                position=0,
                block_type=PublicationBlockType.FILE,
                file="publications/report.pdf",
                youtube_url="https://youtu.be/dQw4w9WgXcQ",
            )

    def test_a_block_with_neither_file_nor_youtube_is_rejected(self, user):
        publication = self._publication(user)

        with transaction.atomic(), pytest.raises(IntegrityError):
            PublicationBlock.objects.create(
                publication=publication,
                position=0,
                block_type=PublicationBlockType.FILE,
            )

    def test_blocks_read_back_in_position_order(self, user):
        publication = self._publication(user)
        PublicationBlock.objects.create(
            publication=publication,
            position=2,
            block_type=PublicationBlockType.YOUTUBE,
            youtube_url="https://youtu.be/two",
        )
        PublicationBlock.objects.create(
            publication=publication,
            position=0,
            block_type=PublicationBlockType.YOUTUBE,
            youtube_url="https://youtu.be/zero",
        )
        PublicationBlock.objects.create(
            publication=publication,
            position=1,
            block_type=PublicationBlockType.YOUTUBE,
            youtube_url="https://youtu.be/one",
        )

        positions = list(publication.blocks.values_list("position", flat=True))

        assert positions == [0, 1, 2]

    def test_deleting_a_publication_cascades_its_blocks(self, user):
        publication = self._publication(user)
        PublicationBlock.objects.create(
            publication=publication,
            position=0,
            block_type=PublicationBlockType.YOUTUBE,
            youtube_url="https://youtu.be/zero",
        )

        publication.delete()

        assert PublicationBlock.objects.count() == 0


@pytest.mark.django_db
class TestSeedResourceTypes:
    def test_seed_creates_ten_types_idempotently(self):
        call_command("seed_resource_types")
        assert ResourceType.objects.count() == 10

        # Running again must not duplicate.
        call_command("seed_resource_types")
        assert ResourceType.objects.count() == 10


@pytest.mark.django_db
class TestPublicationDefaults:
    def test_new_publication_defaults_to_draft(self, user):
        publication = Publication.objects.create(title="Draft one", user=user)

        assert publication.status == PublicationStatus.DRAFT
        assert publication.download_count == 0
        assert publication.authors == []
