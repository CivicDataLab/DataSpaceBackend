"""Layer 1/3/4 tests for content blocks: add/reorder/remove/replace + download gate."""

import os
from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from api.models import Publication, PublicationBlock, ResourceType
from api.models.Organization import Organization
from api.services.publication_blocks import (
    add_file_block,
    add_youtube_block,
    remove_block,
    reorder_blocks,
    replace_block_file,
)
from api.utils.enums import PublicationBlockType, PublicationStatus
from api.views.publication_download_view import publication_block_download
from authorization.models import OrganizationMembership, Role, User

VIDEO = "https://youtu.be/dQw4w9WgXcQ"


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", keycloak_id="owner")


@pytest.fixture
def resource_type(db):
    return ResourceType.objects.create(name="Report")


@pytest.fixture
def publication(owner, resource_type):
    return Publication.objects.create(
        title="With Blocks",
        user=owner,
        resource_type=resource_type,
        publication_date=date(2024, 1, 1),
    )


def _pdf(name="report.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.7 content", content_type="application/pdf")


@pytest.mark.django_db
class TestAddBlocks:
    def test_file_block_stores_metadata_and_position(self, publication):
        block = add_file_block(publication, _pdf())

        assert block.block_type == PublicationBlockType.FILE
        assert block.file_format == "pdf"
        assert block.file_size > 0
        assert block.position == 0

    def test_youtube_block_extracts_video_id(self, publication):
        block = add_youtube_block(publication, VIDEO)

        assert block.block_type == PublicationBlockType.YOUTUBE
        assert block.youtube_video_id == "dQw4w9WgXcQ"

    def test_positions_increment_across_mixed_blocks(self, publication):
        add_file_block(publication, _pdf("a.pdf"))
        add_youtube_block(publication, VIDEO)
        third = add_file_block(publication, _pdf("c.pdf"))

        assert third.position == 2


@pytest.mark.django_db
class TestReorderAndRemove:
    def test_removing_a_middle_block_renumbers_contiguously(self, publication):
        a = add_youtube_block(publication, VIDEO)
        b = add_youtube_block(publication, VIDEO)
        c = add_youtube_block(publication, VIDEO)

        remove_block(b)

        positions = list(publication.blocks.order_by("position").values_list("position", flat=True))
        assert positions == [0, 1]
        a.refresh_from_db()
        c.refresh_from_db()
        assert a.position == 0 and c.position == 1

    def test_reorder_sets_positions_to_requested_order(self, publication):
        a = add_youtube_block(publication, VIDEO)
        b = add_youtube_block(publication, VIDEO)
        c = add_youtube_block(publication, VIDEO)

        reorder_blocks(publication, [c.id, a.id, b.id])

        a.refresh_from_db()
        b.refresh_from_db()
        c.refresh_from_db()
        assert (c.position, a.position, b.position) == (0, 1, 2)


@pytest.mark.django_db
class TestReplaceFile:
    def test_replace_swaps_file_and_removes_the_old_one(self, publication):
        block = add_file_block(publication, _pdf("first.pdf"))
        old_path = block.file.path
        old_id = block.id
        assert os.path.exists(old_path)

        replace_block_file(block, _pdf("second.pdf"))

        assert block.id == old_id  # same row, in-place
        assert block.file_name == "second.pdf"
        assert not os.path.exists(old_path)  # old file removed from disk


@pytest.mark.django_db
class TestDeleteRemovesFile:
    def test_deleting_a_block_removes_its_file(self, publication):
        block = add_file_block(publication, _pdf())
        path = block.file.path
        assert os.path.exists(path)

        block.delete()

        assert not os.path.exists(path)  # post_delete signal cleaned it up


# --------------------------------------------------------------------------- #
# Download gate (Layer 4)
# --------------------------------------------------------------------------- #
@pytest.fixture
def other_org_user(db):
    role = Role.objects.create(name="admin", can_view=True, can_change=True, can_delete=True)
    org = Organization.objects.create(name="Other", description="o", slug="other")
    user = User.objects.create(username="outsider", keycloak_id="outsider")
    OrganizationMembership.objects.create(user=user, organization=org, role=role)
    return user


def _download(user, block_id):
    request = RequestFactory().get(f"/api/publications/blocks/{block_id}/download/")
    request.user = user
    return publication_block_download(request, block_id)


@pytest.mark.django_db
class TestDownloadGate:
    def test_published_file_downloads_and_counts(self, publication, owner):
        publication.status = PublicationStatus.PUBLISHED
        publication.save()
        block = add_file_block(publication, _pdf())

        response = _download(AnonymousUser(), block.id)

        assert response.status_code == 200
        publication.refresh_from_db()
        assert publication.download_count == 1

    def test_draft_file_hidden_from_anonymous(self, publication):
        block = add_file_block(publication, _pdf())

        response = _download(AnonymousUser(), block.id)

        assert response.status_code == 404
        publication.refresh_from_db()
        assert publication.download_count == 0

    def test_draft_file_hidden_from_other_org(self, publication, other_org_user):
        block = add_file_block(publication, _pdf())

        response = _download(other_org_user, block.id)

        assert response.status_code == 404

    def test_owner_can_download_own_draft_file(self, publication, owner):
        block = add_file_block(publication, _pdf())

        response = _download(owner, block.id)

        assert response.status_code == 200

    def test_pdf_is_served_inline(self, publication, owner):
        publication.status = PublicationStatus.PUBLISHED
        publication.save()
        block = add_file_block(publication, _pdf())

        response = _download(AnonymousUser(), block.id)

        assert response["Content-Disposition"].startswith("inline")
