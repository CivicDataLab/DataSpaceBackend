"""Layer 3/4 tests for the publication (Resource) GraphQL surface.

Executes the real schema against the Django test DB with a fake context that
carries the caller's user and org — establishing the layer-4 pattern for this
repo. Activity recording is stubbed so tests exercise the mutation logic, not
the activity-stream plumbing.
"""

import types
from datetime import date
from unittest.mock import patch

import pytest
from django.contrib.auth.models import AnonymousUser

from api.models import Geography, Publication, ResourceType, Sector
from api.models.Organization import Organization
from api.schema.schema import schema
from api.utils.enums import GeoTypes, PublicationStatus
from authorization.models import OrganizationMembership, Role, User


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _no_activity_recording():
    with patch("api.schema.base_mutation.record_activity", return_value=None):
        yield


@pytest.fixture
def roles(db):
    admin = Role.objects.create(
        name="admin", can_view=True, can_add=True, can_change=True, can_delete=True
    )
    editor = Role.objects.create(
        name="editor", can_view=True, can_add=True, can_change=True, can_delete=False
    )
    auditor = Role.objects.create(
        name="auditor", can_view=True, can_add=False, can_change=False, can_delete=False
    )
    return {"admin": admin, "editor": editor, "auditor": auditor}


@pytest.fixture
def org_a(db):
    return Organization.objects.create(name="Org A", description="a", slug="org-a")


@pytest.fixture
def org_b(db):
    return Organization.objects.create(name="Org B", description="b", slug="org-b")


def _member(user, org, role):
    OrganizationMembership.objects.create(user=user, organization=org, role=role)
    return user


@pytest.fixture
def org_a_admin(roles, org_a):
    return _member(
        User.objects.create(username="a_admin", keycloak_id="a_admin"), org_a, roles["admin"]
    )


@pytest.fixture
def org_a_editor(roles, org_a):
    return _member(
        User.objects.create(username="a_editor", keycloak_id="a_editor"), org_a, roles["editor"]
    )


@pytest.fixture
def org_a_auditor(roles, org_a):
    return _member(
        User.objects.create(username="a_auditor", keycloak_id="a_auditor"), org_a, roles["auditor"]
    )


@pytest.fixture
def org_b_admin(roles, org_b):
    return _member(
        User.objects.create(username="b_admin", keycloak_id="b_admin"), org_b, roles["admin"]
    )


@pytest.fixture
def individual(db):
    return User.objects.create(username="solo", keycloak_id="solo")


@pytest.fixture
def resource_type(db):
    return ResourceType.objects.create(name="Report")


@pytest.fixture
def inactive_type(db):
    return ResourceType.objects.create(name="Retired", is_active=False)


@pytest.fixture
def sector(db):
    return Sector.objects.create(name="Health")


@pytest.fixture
def geography(db):
    return Geography.objects.create(name="India", code="IN", type=GeoTypes.COUNTRY)


def ctx(user, organization=None):
    return types.SimpleNamespace(
        user=user,
        context={"organization": organization} if organization else {},
    )


def run(query, context, variables=None):
    return schema.execute_sync(query, variable_values=variables or {}, context_value=context)


def valid_create_vars(resource_type, sector, geography, **overrides):
    variables = {
        "input": {
            "title": "Rainfall Findings",
            "description": "A study of rainfall.",
            "authors": ["Ada Lovelace"],
            "publicationDate": "2024-01-01",
            "license": "CC_BY_4_0_ATTRIBUTION",
            "resourceTypeId": str(resource_type.id),
            "sectorIds": [str(sector.id)],
            "geographyIds": [geography.id],
        }
    }
    variables["input"].update(overrides)
    return variables


CREATE = """
mutation Create($input: CreatePublicationInput!) {
  createPublication(input: $input) {
    success
    errors { fieldErrors { field messages } nonFieldErrors }
    data { id slug status isIndividualPublication organization { id } user { id } }
  }
}
"""

UPDATE = """
mutation Update($input: UpdatePublicationInput!) {
  updatePublication(input: $input) {
    success
    errors { fieldErrors { field messages } }
    data { id title }
  }
}
"""

PUBLISH = """
mutation Publish($id: UUID!) {
  publishPublication(publicationId: $id) { success data { id status } }
}
"""

UNPUBLISH = """
mutation Unpublish($id: UUID!) {
  unpublishPublication(publicationId: $id) { success data { id status } }
}
"""

DELETE = """
mutation Delete($id: UUID!) {
  deletePublication(publicationId: $id) { success data }
}
"""

GET = """
query Get($id: UUID!) {
  getPublication(publicationId: $id) { id status }
}
"""

LIST = """
query List($includePublic: Boolean) {
  publications(includePublic: $includePublic) { id status }
}
"""


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestCreate:
    def test_org_member_creates_org_owned_draft(
        self, org_a_admin, org_a, resource_type, sector, geography
    ):
        result = run(
            CREATE, ctx(org_a_admin, org_a), valid_create_vars(resource_type, sector, geography)
        )

        assert result.errors is None
        payload = result.data["createPublication"]
        assert payload["success"] is True
        assert payload["data"]["status"] == "DRAFT"
        assert payload["data"]["organization"]["id"] == str(org_a.id)
        assert payload["data"]["isIndividualPublication"] is False
        assert Publication.objects.filter(id=payload["data"]["id"]).exists()

    def test_individual_creates_user_owned_draft(
        self, individual, resource_type, sector, geography
    ):
        result = run(CREATE, ctx(individual), valid_create_vars(resource_type, sector, geography))

        payload = result.data["createPublication"]
        assert payload["success"] is True
        assert payload["data"]["isIndividualPublication"] is True
        assert payload["data"]["user"]["id"] == str(individual.id)

    def test_empty_title_still_creates_a_draft(
        self, individual, resource_type, sector, geography
    ):
        result = run(
            CREATE, ctx(individual), valid_create_vars(resource_type, sector, geography, title="")
        )

        payload = result.data["createPublication"]
        assert payload["success"] is True
        assert payload["data"]["status"] == "DRAFT"
        publication = Publication.objects.get(id=payload["data"]["id"])
        assert publication.title.startswith("New publication ")

    def test_title_only_creates_a_draft(self, individual):
        result = run(CREATE, ctx(individual), {"input": {"title": "Just a title"}})

        payload = result.data["createPublication"]
        assert payload["success"] is True
        assert payload["data"]["status"] == "DRAFT"
        publication = Publication.objects.get(id=payload["data"]["id"])
        assert publication.title == "Just a title"
        assert publication.description in (None, "")
        assert publication.authors == []
        assert publication.resource_type_id is None

    def test_empty_input_creates_a_draft(self, individual):
        result = run(CREATE, ctx(individual), {"input": {}})

        payload = result.data["createPublication"]
        assert payload["success"] is True
        publication = Publication.objects.get(id=payload["data"]["id"])
        assert publication.title.startswith("New publication ")
        assert publication.slug.startswith("new-publication-")

    def test_inactive_resource_type_is_rejected(self, individual, inactive_type, sector, geography):
        result = run(CREATE, ctx(individual), valid_create_vars(inactive_type, sector, geography))

        payload = result.data["createPublication"]
        assert payload["success"] is False
        assert Publication.objects.count() == 0

    def test_anonymous_cannot_create(self, resource_type, sector, geography):
        result = run(
            CREATE, ctx(AnonymousUser()), valid_create_vars(resource_type, sector, geography)
        )

        payload = result.data["createPublication"]
        assert payload["success"] is False
        assert Publication.objects.count() == 0


# --------------------------------------------------------------------------- #
# Update / role gating
# --------------------------------------------------------------------------- #
def _make_publication(user, org, resource_type, status=PublicationStatus.DRAFT):
    return Publication.objects.create(
        title="Existing",
        description="d",
        authors=["A"],
        publication_date=date(2024, 1, 1),
        license="CC_BY_4_0_ATTRIBUTION",
        resource_type=resource_type,
        organization=org,
        user=user,
        status=status,
    )


@pytest.mark.django_db
class TestUpdateAndRoles:
    def test_editor_updates_org_publication(self, org_a_admin, org_a_editor, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(
            UPDATE,
            ctx(org_a_editor, org_a),
            {"input": {"id": str(publication.id), "title": "New Title"}},
        )

        assert result.data["updatePublication"]["success"] is True
        publication.refresh_from_db()
        assert publication.title == "New Title"

    def test_auditor_cannot_update(self, org_a_admin, org_a_auditor, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(
            UPDATE,
            ctx(org_a_auditor, org_a),
            {"input": {"id": str(publication.id), "title": "Hijack"}},
        )

        assert result.data["updatePublication"]["success"] is False
        publication.refresh_from_db()
        assert publication.title == "Existing"

    def test_auditor_can_read_draft(self, org_a_admin, org_a_auditor, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(GET, ctx(org_a_auditor, org_a), {"id": str(publication.id)})

        assert result.errors is None
        assert result.data["getPublication"]["id"] == str(publication.id)


# --------------------------------------------------------------------------- #
# Publish / unpublish
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestPublish:
    def test_admin_publishes(self, org_a_admin, org_a, resource_type, sector, geography):
        publication = _make_publication(org_a_admin, org_a, resource_type)
        publication.sectors.add(sector)
        publication.geographies.add(geography)

        result = run(PUBLISH, ctx(org_a_admin, org_a), {"id": str(publication.id)})

        assert result.data["publishPublication"]["success"] is True
        publication.refresh_from_db()
        assert publication.status == PublicationStatus.PUBLISHED

    def test_auditor_cannot_publish(self, org_a_admin, org_a_auditor, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(PUBLISH, ctx(org_a_auditor, org_a), {"id": str(publication.id)})

        assert result.data["publishPublication"]["success"] is False
        publication.refresh_from_db()
        assert publication.status == PublicationStatus.DRAFT

    def test_unpublish_reverts_to_draft(self, org_a_admin, org_a, resource_type):
        publication = _make_publication(
            org_a_admin, org_a, resource_type, status=PublicationStatus.PUBLISHED
        )

        result = run(UNPUBLISH, ctx(org_a_admin, org_a), {"id": str(publication.id)})

        assert result.data["unpublishPublication"]["success"] is True
        publication.refresh_from_db()
        assert publication.status == PublicationStatus.DRAFT

    def test_publish_rejects_an_incomplete_draft(self, org_a_admin, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(PUBLISH, ctx(org_a_admin, org_a), {"id": str(publication.id)})

        assert result.data["publishPublication"]["success"] is False
        publication.refresh_from_db()
        assert publication.status == PublicationStatus.DRAFT


def _published(user, org, resource_type, sector, geography):
    publication = _make_publication(
        user, org, resource_type, status=PublicationStatus.PUBLISHED
    )
    publication.sectors.add(sector)
    publication.geographies.add(geography)
    return publication


@pytest.mark.django_db
class TestPublicationTags:
    def test_unknown_sector_is_rejected_and_the_row_is_unchanged(
        self, org_a_admin, org_a, resource_type, sector, geography
    ):
        publication = _published(org_a_admin, org_a, resource_type, sector, geography)

        result = run(
            UPDATE,
            ctx(org_a_admin, org_a),
            {
                "input": {
                    "id": str(publication.id),
                    "title": "Should not stick",
                    "sectorIds": ["00000000-0000-0000-0000-000000000000"],
                }
            },
        )

        assert result.data["updatePublication"]["success"] is False
        fields = [
            error["field"]
            for error in result.data["updatePublication"]["errors"]["fieldErrors"]
        ]
        assert "sectors" in fields
        publication.refresh_from_db()
        assert publication.title == "Existing"
        assert list(publication.sectors.values_list("id", flat=True)) == [sector.id]

    def test_null_tag_lists_leave_published_tags_in_place(
        self, org_a_admin, org_a, resource_type, sector, geography
    ):
        publication = _published(org_a_admin, org_a, resource_type, sector, geography)

        result = run(
            UPDATE,
            ctx(org_a_admin, org_a),
            {
                "input": {
                    "id": str(publication.id),
                    "title": "Renamed",
                    "sectorIds": None,
                    "geographyIds": None,
                }
            },
        )

        assert result.data["updatePublication"]["success"] is True
        publication.refresh_from_db()
        assert publication.title == "Renamed"
        assert list(publication.sectors.values_list("id", flat=True)) == [sector.id]
        assert list(publication.geographies.values_list("id", flat=True)) == [geography.id]

    def test_create_rejects_an_unknown_geography(
        self, individual, resource_type, sector, geography
    ):
        result = run(
            CREATE,
            ctx(individual),
            valid_create_vars(resource_type, sector, geography, geographyIds=[999999999]),
        )

        assert result.data["createPublication"]["success"] is False
        assert Publication.objects.count() == 0


# --------------------------------------------------------------------------- #
# Cross-org denial
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestCrossOrgDenial:
    def test_other_org_cannot_update(self, org_a_admin, org_b_admin, org_a, org_b, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(
            UPDATE,
            ctx(org_b_admin, org_b),
            {"input": {"id": str(publication.id), "title": "Steal"}},
        )

        assert result.data["updatePublication"]["success"] is False
        publication.refresh_from_db()
        assert publication.title == "Existing"

    def test_other_org_cannot_delete(self, org_a_admin, org_b_admin, org_a, org_b, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(DELETE, ctx(org_b_admin, org_b), {"id": str(publication.id)})

        assert result.data["deletePublication"]["success"] is False
        assert Publication.objects.filter(id=publication.id).exists()

    def test_other_org_cannot_publish(self, org_a_admin, org_b_admin, org_a, org_b, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(PUBLISH, ctx(org_b_admin, org_b), {"id": str(publication.id)})

        assert result.data["publishPublication"]["success"] is False
        publication.refresh_from_db()
        assert publication.status == PublicationStatus.DRAFT


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestDelete:
    def test_owner_deletes(self, org_a_admin, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(DELETE, ctx(org_a_admin, org_a), {"id": str(publication.id)})

        assert result.data["deletePublication"]["success"] is True
        assert not Publication.objects.filter(id=publication.id).exists()


# --------------------------------------------------------------------------- #
# Read gating + listing
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestReadGating:
    def test_anonymous_sees_published_detail(self, org_a_admin, org_a, resource_type):
        publication = _make_publication(
            org_a_admin, org_a, resource_type, status=PublicationStatus.PUBLISHED
        )

        result = run(GET, ctx(AnonymousUser()), {"id": str(publication.id)})

        assert result.errors is None
        assert result.data["getPublication"]["id"] == str(publication.id)

    def test_anonymous_denied_draft_detail(self, org_a_admin, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(GET, ctx(AnonymousUser()), {"id": str(publication.id)})

        assert result.errors is not None  # permission denied, not a silent leak

    def test_listing_is_org_scoped(self, org_a_admin, org_b_admin, org_a, org_b, resource_type):
        _make_publication(org_a_admin, org_a, resource_type)
        _make_publication(org_b_admin, org_b, resource_type)

        result = run(LIST, ctx(org_a_admin, org_a), {"includePublic": False})

        assert result.errors is None
        assert len(result.data["publications"]) == 1

    def test_anonymous_listing_is_published_only(self, org_a_admin, org_a, resource_type):
        _make_publication(org_a_admin, org_a, resource_type, status=PublicationStatus.DRAFT)
        _make_publication(org_a_admin, org_a, resource_type, status=PublicationStatus.PUBLISHED)

        result = run(LIST, ctx(AnonymousUser()), {"includePublic": False})

        statuses = [row["status"] for row in result.data["publications"]]
        assert statuses == ["PUBLISHED"]


# --------------------------------------------------------------------------- #
# Content-block mutations (wiring + cross-org gate)
# --------------------------------------------------------------------------- #
ADD_YOUTUBE = """
mutation AddYt($id: UUID!, $url: String!, $title: String, $description: String) {
  addPublicationYoutubeBlock(
    publicationId: $id
    youtubeUrl: $url
    title: $title
    description: $description
  ) {
    success
    data { id blockType youtubeVideoId position title description created }
  }
}
"""

UPDATE_BLOCK = """
mutation UpdateBlock($blockId: UUID!, $title: String, $description: String) {
  updatePublicationBlock(blockId: $blockId, title: $title, description: $description) {
    success
    data { id title description }
  }
}
"""

REMOVE_BLOCK = """
mutation RemoveBlock($blockId: UUID!) {
  removePublicationBlock(blockId: $blockId) { success data }
}
"""


@pytest.mark.django_db
class TestBlockMutations:
    def test_org_member_adds_youtube_block(self, org_a_admin, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(
            ADD_YOUTUBE,
            ctx(org_a_admin, org_a),
            {"id": str(publication.id), "url": "https://youtu.be/dQw4w9WgXcQ"},
        )

        payload = result.data["addPublicationYoutubeBlock"]
        assert payload["success"] is True
        assert payload["data"]["youtubeVideoId"] == "dQw4w9WgXcQ"
        assert payload["data"]["title"] == ""
        assert payload["data"]["created"]
        assert publication.blocks.count() == 1

    def test_block_title_and_description_can_be_set(self, org_a_admin, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)
        created = run(
            ADD_YOUTUBE,
            ctx(org_a_admin, org_a),
            {
                "id": str(publication.id),
                "url": "https://youtu.be/dQw4w9WgXcQ",
                "title": "Launch talk",
                "description": "Opening remarks",
            },
        )
        block_id = created.data["addPublicationYoutubeBlock"]["data"]["id"]

        renamed = run(
            UPDATE_BLOCK,
            ctx(org_a_admin, org_a),
            {"blockId": block_id, "title": "Renamed talk"},
        )

        assert renamed.data["updatePublicationBlock"]["success"] is True
        assert renamed.data["updatePublicationBlock"]["data"]["title"] == "Renamed talk"
        assert renamed.data["updatePublicationBlock"]["data"]["description"] == "Opening remarks"

    def test_invalid_youtube_url_is_rejected(self, org_a_admin, org_a, resource_type):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(
            ADD_YOUTUBE,
            ctx(org_a_admin, org_a),
            {"id": str(publication.id), "url": "https://vimeo.com/1"},
        )

        assert result.data["addPublicationYoutubeBlock"]["success"] is False
        assert publication.blocks.count() == 0

    def test_other_org_cannot_add_block(
        self, org_a_admin, org_b_admin, org_a, org_b, resource_type
    ):
        publication = _make_publication(org_a_admin, org_a, resource_type)

        result = run(
            ADD_YOUTUBE,
            ctx(org_b_admin, org_b),
            {"id": str(publication.id), "url": "https://youtu.be/dQw4w9WgXcQ"},
        )

        assert result.data["addPublicationYoutubeBlock"]["success"] is False
        assert publication.blocks.count() == 0

    def test_other_org_cannot_remove_block(
        self, org_a_admin, org_b_admin, org_a, org_b, resource_type
    ):
        publication = _make_publication(org_a_admin, org_a, resource_type)
        block = publication.blocks.create(
            position=0,
            block_type="YOUTUBE",
            youtube_url="https://youtu.be/dQw4w9WgXcQ",
            youtube_video_id="dQw4w9WgXcQ",
        )

        result = run(REMOVE_BLOCK, ctx(org_b_admin, org_b), {"blockId": str(block.id)})

        assert result.data["removePublicationBlock"]["success"] is False
        assert publication.blocks.filter(id=block.id).exists()


RESOURCE_TYPES = "query { resourceTypes { id name isActive } }"


@pytest.mark.django_db
class TestResourceTypesQuery:
    def test_lists_only_active_types_sorted(self, resource_type, inactive_type):
        result = run(RESOURCE_TYPES, ctx(AnonymousUser()))

        assert result.errors is None
        names = [t["name"] for t in result.data["resourceTypes"]]
        assert names == ["Report"]  # active only; "Retired" excluded
