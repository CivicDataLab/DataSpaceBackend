"""Publication fields keep to the platform's limits (DataSpaceBackend#327).

Root cause: publication mutations save without ``full_clean`` and the service
checked only the link's shape with ``URLValidator()``, whose default schemes
include ftp/ftps. Nothing limited the date, the description, the title, the
link's length or the number of people, so the API stored values the wizard
would never send (and a title over 300 or a link over 200 characters failed in
Postgres instead of returning a message).

Fix: ``publication_service`` refuses non-http(s) links, links and titles longer
than their columns, descriptions over 1000 characters (as datasets,
organisations and charts), future dates (as the dataset form) and more than 50
contributors or authors. Drafts are checked on what was sent; publishing and
edits to a published publication check every stored value.
"""

import datetime
import types
from unittest.mock import patch

import pytest

from api.models import Geography, Publication, ResourceType, Sector
from api.models.Organization import Organization
from api.schema.schema import schema
from api.services.publication_service import DESCRIPTION_MAX_LENGTH, MAX_CONTRIBUTORS
from api.utils.enums import GeoTypes, PublicationStatus
from authorization.models import OrganizationMembership, Role, User


@pytest.fixture(autouse=True)
def _no_activity_recording():
    with patch("api.schema.base_mutation.record_activity", return_value=None):
        yield


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org A", description="a", slug="org-a")


@pytest.fixture
def admin(org):
    role = Role.objects.create(
        name="admin", can_view=True, can_add=True, can_change=True, can_delete=True
    )
    user = User.objects.create(username="a_admin", keycloak_id="a_admin")
    OrganizationMembership.objects.create(user=user, organization=org, role=role)
    return user


@pytest.fixture
def ready(db):
    return {
        "resource_type": ResourceType.objects.create(name="Report"),
        "sector": Sector.objects.create(name="Health"),
        "geography": Geography.objects.create(name="India", code="IN", type=GeoTypes.COUNTRY),
    }


def ctx(user, organization=None):
    return types.SimpleNamespace(
        user=user, context={"organization": organization} if organization else {}
    )


def run(query, context, variables):
    return schema.execute_sync(query, variable_values=variables, context_value=context)


CREATE = """
mutation Create($input: CreatePublicationInput!) {
  createPublication(input: $input) {
    success
    errors { fieldErrors { field messages } }
    data { id }
  }
}
"""

UPDATE = """
mutation Update($input: UpdatePublicationInput!) {
  updatePublication(input: $input) {
    success
    errors { fieldErrors { field messages } }
  }
}
"""

PUBLISH = """
mutation Publish($id: UUID!) {
  publishPublication(publicationId: $id) {
    success
    errors { fieldErrors { field messages } }
  }
}
"""


def _publication(owner, org, ready, **fields):
    values = {
        "title": "Water report",
        "description": "d",
        "authors": ["Old Name"],
        "publication_date": datetime.date(2024, 1, 1),
        "license": "CC_BY_4_0_ATTRIBUTION",
        "resource_type": ready["resource_type"],
        "organization": org,
        "user": owner,
        "status": PublicationStatus.DRAFT,
    }
    values.update(fields)
    publication = Publication.objects.create(**values)
    publication.sectors.add(ready["sector"])
    publication.geographies.add(ready["geography"])
    return publication


def _errors(payload):
    return {
        item["field"]: item["messages"]
        for item in (payload["errors"] or {}).get("fieldErrors") or []
    }


def _utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date()


def _create(admin, org, **input_fields):
    payload = run(CREATE, ctx(admin, org), {"input": {"title": "T", **input_fields}})
    return payload.data["createPublication"]


def _update(admin, org, publication, **input_fields):
    payload = run(UPDATE, ctx(admin, org), {"input": {"id": str(publication.id), **input_fields}})
    return payload.data["updatePublication"]


# --------------------------------------------------------------------------- #
# External link
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestLink:
    @pytest.mark.parametrize("link", ["ftp://files.example.org/r.pdf", "ftps://example.org/r"])
    def test_non_http_link_is_refused_on_create(self, admin, org, link):
        result = _create(admin, org, externalSourceLink=link)

        assert result["success"] is False
        assert _errors(result) == {"external_source_link": ["Enter a valid URL."]}
        assert Publication.objects.count() == 0

    def test_non_http_link_is_refused_on_update(self, admin, org, ready):
        publication = _publication(admin, org, ready, external_source_link="https://a.org")

        result = _update(admin, org, publication, externalSourceLink="ftp://a.org/r.pdf")

        assert _errors(result) == {"external_source_link": ["Enter a valid URL."]}
        publication.refresh_from_db()
        assert publication.external_source_link == "https://a.org"

    def test_https_link_is_saved(self, admin, org):
        result = _create(admin, org, externalSourceLink="https://example.org/report")

        assert result["success"] is True
        assert Publication.objects.get().external_source_link == "https://example.org/report"

    def test_link_longer_than_its_column_is_refused(self, admin, org):
        link = "https://example.org/" + "a" * 200

        result = _create(admin, org, externalSourceLink=link)

        assert _errors(result) == {
            "external_source_link": ["External source link cannot be longer than 200 characters."]
        }

    def test_empty_link_still_clears(self, admin, org, ready):
        publication = _publication(admin, org, ready, external_source_link="https://a.org")

        result = _update(admin, org, publication, externalSourceLink="")

        assert result["success"] is True
        publication.refresh_from_db()
        assert publication.external_source_link is None


# --------------------------------------------------------------------------- #
# Date, title, description
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestDateAndText:
    @pytest.mark.parametrize("days_ahead", [2, 365])
    def test_future_date_is_refused(self, admin, org, days_ahead):
        date = _utc_today() + datetime.timedelta(days=days_ahead)

        result = _create(admin, org, publicationDate=date.isoformat())

        assert _errors(result) == {
            "publication_date": ["Publication date cannot be in the future."]
        }

    def test_far_future_date_from_the_issue_is_refused(self, admin, org, ready):
        publication = _publication(admin, org, ready)

        result = _update(admin, org, publication, publicationDate="9999-12-31")

        assert "publication_date" in _errors(result)
        publication.refresh_from_db()
        assert publication.publication_date == datetime.date(2024, 1, 1)

    @pytest.mark.parametrize("days_ahead", [-3650, 0, 1])
    def test_past_today_and_users_ahead_of_utc_are_accepted(self, admin, org, days_ahead):
        """+1: a user in India can be on tomorrow's date while the server (UTC) is not."""
        date = _utc_today() + datetime.timedelta(days=days_ahead)

        result = _create(admin, org, publicationDate=date.isoformat())

        assert result["success"] is True

    def test_description_over_the_limit_is_refused(self, admin, org):
        result = _create(admin, org, description="x" * (DESCRIPTION_MAX_LENGTH + 1))

        assert _errors(result) == {
            "description": [
                f"Description cannot be longer than {DESCRIPTION_MAX_LENGTH} characters."
            ]
        }

    def test_description_at_the_limit_is_saved(self, admin, org):
        result = _create(admin, org, description="x" * DESCRIPTION_MAX_LENGTH)

        assert result["success"] is True

    def test_title_longer_than_its_column_is_refused(self, admin, org, ready):
        publication = _publication(admin, org, ready)

        result = _update(admin, org, publication, title="t" * 301)

        assert _errors(result) == {"title": ["Title cannot be longer than 300 characters."]}
        publication.refresh_from_db()
        assert publication.title == "Water report"


# --------------------------------------------------------------------------- #
# Number of people
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestPeople:
    def test_too_many_contributor_ids_are_refused_before_lookup(self, admin, org):
        ids = [str(number) for number in range(1, MAX_CONTRIBUTORS + 2)]

        result = _create(admin, org, contributorIds=ids)

        assert _errors(result) == {
            "contributors": [f"A publication can have at most {MAX_CONTRIBUTORS} contributors."]
        }

    def test_limit_counts_each_contributor_once(self, admin, org):
        result = _create(admin, org, contributorIds=[str(admin.id)] * (MAX_CONTRIBUTORS + 5))

        assert result["success"] is True

    def test_too_many_author_names_are_refused(self, admin, org, ready):
        publication = _publication(admin, org, ready)
        names = [f"Person {number}" for number in range(MAX_CONTRIBUTORS + 1)]

        result = _update(admin, org, publication, authors=names)

        assert _errors(result) == {
            "authors": [f"A publication can have at most {MAX_CONTRIBUTORS} authors."]
        }


# --------------------------------------------------------------------------- #
# Values saved before these checks
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestOlderValues:
    def test_draft_edit_checks_only_what_was_sent(self, admin, org, ready):
        publication = _publication(admin, org, ready, description="x" * 5000)

        result = _update(admin, org, publication, title="New title")

        assert result["success"] is True

    def test_publish_refuses_an_older_far_future_date(self, admin, org, ready):
        publication = _publication(admin, org, ready, publication_date=datetime.date(9999, 12, 31))

        result = run(PUBLISH, ctx(admin, org), {"id": str(publication.id)})

        payload = result.data["publishPublication"]
        assert payload["success"] is False
        assert "publication_date" in _errors(payload)

    def test_publish_refuses_an_older_ftp_link(self, admin, org, ready):
        publication = _publication(admin, org, ready, external_source_link="ftp://a.org/r.pdf")

        result = run(PUBLISH, ctx(admin, org), {"id": str(publication.id)})

        assert "external_source_link" in _errors(result.data["publishPublication"])
