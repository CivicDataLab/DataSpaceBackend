"""GraphQL tests for the event provider."""

import types
from datetime import date
from unittest.mock import patch

import pytest
from django.contrib.auth.models import AnonymousUser

from api.models import Event
from api.models.Organization import Organization
from api.schema.schema import schema
from api.utils.enums import EventStatus
from api.utils.luma import extract_luma_embed_url, parse_luma_embed
from authorization.models import OrganizationMembership, Role, User

EMBED = "https://lu.ma/embed/event/evt-abc/simple"
IFRAME = (
    f'<iframe src="{EMBED}" width="600" height="450" '
    'style="border: 1px solid #bfcbda88; border-radius: 4px;" allowfullscreen></iframe>'
)


@pytest.fixture(autouse=True)
def _no_activity_recording():
    with patch("api.schema.base_mutation.record_activity", return_value=None):
        yield


@pytest.fixture
def roles(db):
    admin = Role.objects.create(
        name="admin", can_view=True, can_add=True, can_change=True, can_delete=True
    )
    auditor = Role.objects.create(
        name="auditor", can_view=True, can_add=False, can_change=False, can_delete=False
    )
    return {"admin": admin, "auditor": auditor}


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
        User.objects.create(username="event_a_admin", keycloak_id="event_a_admin"),
        org_a,
        roles["admin"],
    )


@pytest.fixture
def org_a_auditor(roles, org_a):
    return _member(
        User.objects.create(username="event_a_auditor", keycloak_id="event_a_auditor"),
        org_a,
        roles["auditor"],
    )


@pytest.fixture
def org_b_admin(roles, org_b):
    return _member(
        User.objects.create(username="event_b_admin", keycloak_id="event_b_admin"),
        org_b,
        roles["admin"],
    )


@pytest.fixture
def individual(db):
    return User.objects.create(username="event_solo", keycloak_id="event_solo")


def ctx(user, organization=None):
    return types.SimpleNamespace(
        user=user,
        context={"organization": organization} if organization else {},
    )


def run(query, context, variables=None):
    return schema.execute_sync(query, variable_values=variables or {}, context_value=context)


def _make_event(user, org, **overrides):
    values = {
        "name": "Existing meetup",
        "location": "Pune",
        "start_date": date(2026, 6, 1),
        "end_date": date(2026, 6, 2),
        "luma_embed": {"src": EMBED},
        "organization": org,
        "user": user,
        "status": EventStatus.DRAFT,
    }
    values.update(overrides)
    return Event.objects.create(**values)


CREATE = """
mutation Create($input: CreateEventInput!) {
  createEvent(input: $input) {
    success
    errors { nonFieldErrors fieldErrors { field messages } }
    data { id status isIndividualEvent organization { id } user { id } }
  }
}
"""

UPDATE = """
mutation Update($input: UpdateEventInput!) {
  updateEvent(input: $input) {
    success
    errors { fieldErrors { field messages } nonFieldErrors }
    data { id name location startDate endDate lumaEmbed { src width height style allowfullscreen } }
  }
}
"""

PUBLISH = """
mutation Publish($id: UUID!) {
  publishEvent(eventId: $id) {
    success
    errors { fieldErrors { field messages } nonFieldErrors }
    data { id status }
  }
}
"""

TABLE = """
query Events($filters: [FilterSpec!]) {
  eventsTable(filters: $filters) {
    totalItemsCount
    data { id status name }
  }
}
"""

GET = """
query Get($id: UUID!) {
  event(eventId: $id) { id status }
}
"""

PUBLISHED = """
query Published($organizationSlug: String) {
  publishedEvents(organizationSlug: $organizationSlug) {
    totalItemsCount
    data { name slug status organization { slug } }
  }
}
"""

BY_SLUG = """
query BySlug($slug: String!) {
  eventBySlug(slug: $slug) { name urlSlug status lumaEmbed { src } }
}
"""


def test_iframe_keeps_presentation_attributes():
    embed = parse_luma_embed(IFRAME)
    assert embed is not None
    assert embed["src"] == EMBED
    assert embed["width"] == "600"
    assert embed["height"] == "450"
    assert embed["allowfullscreen"] is True
    assert "border-radius" in str(embed["style"])


def test_iframe_src_becomes_a_canonical_embed_url():
    assert extract_luma_embed_url(IFRAME) == EMBED


def test_script_and_event_handlers_are_rejected():
    assert parse_luma_embed(f'<iframe src="{EMBED}" onload="alert(1)"></iframe>') is None
    assert parse_luma_embed(f'<script></script><iframe src="{EMBED}"></iframe>') is None


def test_non_embed_luma_page_is_rejected():
    assert extract_luma_embed_url("https://lu.ma/community-meetup") is None
    assert extract_luma_embed_url("http://lu.ma/embed/event/evt-abc/simple") is None
    assert extract_luma_embed_url("https://evil.example/embed/event/evt-abc") is None


@pytest.mark.django_db
class TestEventSchema:
    def test_org_member_creates_an_org_draft(self, org_a_admin, org_a):
        result = run(CREATE, ctx(org_a_admin, org_a), {"input": {}})

        assert result.errors is None
        payload = result.data["createEvent"]
        assert payload["success"] is True
        assert payload["data"]["status"] == "DRAFT"
        assert payload["data"]["organization"]["id"] == str(org_a.id)
        assert payload["data"]["isIndividualEvent"] is False

    def test_individual_creates_a_user_owned_draft(self, individual):
        result = run(CREATE, ctx(individual), {"input": {"name": "Solo night"}})

        payload = result.data["createEvent"]
        assert payload["success"] is True
        assert payload["data"]["isIndividualEvent"] is True
        assert payload["data"]["user"]["id"] == str(individual.id)

    def test_auditor_cannot_create(self, org_a_auditor, org_a):
        result = run(CREATE, ctx(org_a_auditor, org_a), {"input": {}})

        assert result.data["createEvent"]["success"] is False
        assert Event.objects.count() == 0

    def test_anonymous_cannot_create(self):
        result = run(CREATE, ctx(AnonymousUser()), {"input": {}})

        assert result.data["createEvent"]["success"] is False

    def test_invalid_embed_is_rejected(self, individual):
        created = run(CREATE, ctx(individual), {"input": {}})
        event_id = created.data["createEvent"]["data"]["id"]

        result = run(
            UPDATE,
            ctx(individual),
            {"input": {"id": event_id, "lumaEmbed": "https://youtu.be/dQw4w9WgXcQ"}},
        )

        assert result.data["updateEvent"]["success"] is False
        event = Event.objects.get(id=event_id)
        assert event.luma_embed == {}

    def test_iframe_is_stored_as_the_embed_url(self, individual):
        created = run(CREATE, ctx(individual), {"input": {}})
        event_id = created.data["createEvent"]["data"]["id"]

        result = run(
            UPDATE,
            ctx(individual),
            {
                "input": {
                    "id": event_id,
                    "name": "Community meetup",
                    "location": "Pune",
                    "startDate": "2026-06-01",
                    "endDate": "2026-06-02",
                    "lumaEmbed": IFRAME,
                }
            },
        )

        payload = result.data["updateEvent"]
        assert result.errors is None
        assert payload["success"] is True
        assert payload["data"]["lumaEmbed"]["src"] == EMBED
        assert payload["data"]["lumaEmbed"]["width"] == "600"
        assert payload["data"]["lumaEmbed"]["height"] == "450"
        assert payload["data"]["lumaEmbed"]["allowfullscreen"] is True

    def test_end_date_before_start_is_rejected(self, individual):
        created = run(CREATE, ctx(individual), {"input": {}})
        event_id = created.data["createEvent"]["data"]["id"]

        result = run(
            UPDATE,
            ctx(individual),
            {"input": {"id": event_id, "startDate": "2026-06-02", "endDate": "2026-06-01"}},
        )

        assert result.data["updateEvent"]["success"] is False

    def test_publish_rejects_an_incomplete_draft(self, org_a_admin, org_a):
        event = _make_event(org_a_admin, org_a, location="", luma_embed={})

        result = run(PUBLISH, ctx(org_a_admin, org_a), {"id": str(event.id)})

        assert result.data["publishEvent"]["success"] is False
        event.refresh_from_db()
        assert event.status == EventStatus.DRAFT

    def test_publish_accepts_a_complete_event(self, org_a_admin, org_a):
        event = _make_event(org_a_admin, org_a)

        result = run(PUBLISH, ctx(org_a_admin, org_a), {"id": str(event.id)})

        assert result.errors is None
        assert result.data["publishEvent"]["success"] is True
        assert result.data["publishEvent"]["data"]["status"] == "PUBLISHED"

    def test_listing_is_org_scoped(self, org_a_admin, org_b_admin, org_a, org_b):
        _make_event(org_a_admin, org_a)
        _make_event(org_b_admin, org_b, name="Other org")

        result = run(TABLE, ctx(org_a_admin, org_a))

        assert result.errors is None
        names = [row["name"] for row in result.data["eventsTable"]["data"]]
        assert names == ["Existing meetup"]

    def test_anonymous_listing_is_published_only(self, org_a_admin, org_a):
        _make_event(org_a_admin, org_a, name="Draft night")
        _make_event(org_a_admin, org_a, name="Public night", status=EventStatus.PUBLISHED)

        result = run(TABLE, ctx(AnonymousUser()))

        statuses = [row["status"] for row in result.data["eventsTable"]["data"]]
        assert statuses == ["PUBLISHED"]

    def test_published_listing_is_public_for_a_signed_in_user(
        self, org_a_admin, org_b_admin, org_a, org_b, individual
    ):
        _make_event(org_a_admin, org_a, name="Draft night")
        _make_event(
            org_a_admin,
            org_a,
            name="Public night",
            status=EventStatus.PUBLISHED,
            start_date=date(2026, 6, 2),
        )
        _make_event(
            org_b_admin,
            org_b,
            name="Other public",
            status=EventStatus.PUBLISHED,
            start_date=date(2026, 6, 1),
        )

        result = run(PUBLISHED, ctx(individual))

        assert result.errors is None
        names = [row["name"] for row in result.data["publishedEvents"]["data"]]
        assert names == ["Other public", "Public night"]
        assert result.data["publishedEvents"]["totalItemsCount"] == 2

    def test_published_listing_can_be_limited_to_one_organization(
        self, org_a_admin, org_b_admin, org_a, org_b
    ):
        _make_event(org_a_admin, org_a, name="Public night", status=EventStatus.PUBLISHED)
        _make_event(org_b_admin, org_b, name="Other public", status=EventStatus.PUBLISHED)

        result = run(PUBLISHED, ctx(AnonymousUser()), {"organizationSlug": "org-a"})

        names = [row["name"] for row in result.data["publishedEvents"]["data"]]
        assert names == ["Public night"]

    def test_event_by_slug_returns_a_published_event(self, org_a_admin, org_a):
        event = _make_event(org_a_admin, org_a, name="Public night", status=EventStatus.PUBLISHED)

        result = run(BY_SLUG, ctx(AnonymousUser()), {"slug": event.url_slug})

        assert result.errors is None
        assert result.data["eventBySlug"]["urlSlug"] == event.url_slug
        assert result.data["eventBySlug"]["lumaEmbed"]["src"] == EMBED

    def test_event_by_slug_hides_drafts(self, org_a_admin, org_a):
        event = _make_event(org_a_admin, org_a, name="Draft night")

        result = run(BY_SLUG, ctx(AnonymousUser()), {"slug": event.url_slug})

        assert result.errors is None
        assert result.data["eventBySlug"] is None

    def test_anonymous_cannot_read_a_draft(self, org_a_admin, org_a):
        event = _make_event(org_a_admin, org_a)

        result = run(GET, ctx(AnonymousUser()), {"id": str(event.id)})

        assert result.errors is not None

    def test_other_org_cannot_update(self, org_a_admin, org_b_admin, org_a, org_b):
        event = _make_event(org_a_admin, org_a)

        result = run(
            UPDATE,
            ctx(org_b_admin, org_b),
            {"input": {"id": str(event.id), "name": "Taken"}},
        )

        assert result.data["updateEvent"]["success"] is False
        event.refresh_from_db()
        assert event.name == "Existing meetup"
