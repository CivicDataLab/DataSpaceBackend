"""Publication contributors are linked users, not saved names.

Root cause: the publication wizard picked real users from ``searchUsers`` but
saved only their display name in ``Publication.authors`` (a list of strings).
Users without a first or last name were saved as their username, a renamed
user kept the old name, and the frontend rebuilt fake ids from names on
reload, so the same person could be added twice (DataSpaceFrontend#560).

Fix: ``Publication.contributors`` links users. Create/update take
``contributorIds`` (sending them clears the old names), the publication returns
``contributors`` (emails only for editors), publishing accepts a contributor
or an old name, and migration 0068 links the names already saved.
"""

import importlib
import io
import types
from datetime import date
from unittest.mock import patch

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command

from api.models import Geography, Publication, ResourceType, Sector
from api.models.Organization import Organization
from api.schema.schema import schema
from api.utils.enums import GeoTypes, PublicationStatus
from api.utils.publication_contributors import (
    display_name,
    index_users,
    match_author,
    split_authors,
)
from authorization.models import OrganizationMembership, Role, User

link_migration = importlib.import_module("api.migrations.0068_link_publication_contributors")


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
    user = User.objects.create(username="a_admin", keycloak_id="a_admin", email="admin@x.org")
    OrganizationMembership.objects.create(user=user, organization=org, role=role)
    return user


@pytest.fixture
def priya(db):
    return User.objects.create(
        username="priya_s",
        keycloak_id="priya",
        first_name="Priya",
        last_name="Sharma",
        email="priya@x.org",
    )


@pytest.fixture
def ada(db):
    return User.objects.create(username="ada_k", keycloak_id="ada", email="ada@x.org")


@pytest.fixture
def outsider(db):
    return User.objects.create(username="outsider", keycloak_id="outsider")


@pytest.fixture
def ready(db):
    """Everything except people that a publish needs."""
    return {
        "resource_type": ResourceType.objects.create(name="Report"),
        "sector": Sector.objects.create(name="Health"),
        "geography": Geography.objects.create(name="India", code="IN", type=GeoTypes.COUNTRY),
    }


def ctx(user, organization=None):
    return types.SimpleNamespace(
        user=user, context={"organization": organization} if organization else {}
    )


def run(query, context, variables=None):
    return schema.execute_sync(query, variable_values=variables or {}, context_value=context)


CREATE = """
mutation Create($input: CreatePublicationInput!) {
  createPublication(input: $input) {
    success
    errors { fieldErrors { field messages } }
    data { id authors contributors { id fullName email } }
  }
}
"""

UPDATE = """
mutation Update($input: UpdatePublicationInput!) {
  updatePublication(input: $input) {
    success
    errors { fieldErrors { field messages } }
    data { id authors contributors { id } }
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

GET = """
query Get($id: UUID!) {
  getPublication(publicationId: $id) { contributors { id fullName email } }
}
"""


def _publication(owner, org, ready, status=PublicationStatus.DRAFT, authors=()):
    publication = Publication.objects.create(
        title="Water report",
        description="d",
        authors=list(authors),
        publication_date=date(2024, 1, 1),
        license="CC_BY_4_0_ATTRIBUTION",
        resource_type=ready["resource_type"],
        organization=org,
        user=owner,
        status=status,
    )
    publication.sectors.add(ready["sector"])
    publication.geographies.add(ready["geography"])
    return publication


def _ids(rows):
    return sorted(int(row["id"]) for row in rows)


def _field_errors(payload):
    return {item["field"] for item in (payload["errors"] or {}).get("fieldErrors") or []}


# --------------------------------------------------------------------------- #
# Saving contributors
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestSaveContributors:
    def test_create_links_users_and_clears_names(self, admin, org, priya, ada):
        result = run(
            CREATE,
            ctx(admin, org),
            {"input": {"authors": ["ada_k"], "contributorIds": [str(priya.id), str(ada.id)]}},
        )

        payload = result.data["createPublication"]
        assert payload["success"] is True, payload
        assert _ids(payload["data"]["contributors"]) == sorted([priya.id, ada.id])
        assert payload["data"]["authors"] == []

    def test_repeated_id_is_saved_once(self, admin, org, priya):
        result = run(
            CREATE, ctx(admin, org), {"input": {"contributorIds": [str(priya.id), str(priya.id)]}}
        )

        publication = Publication.objects.get(id=result.data["createPublication"]["data"]["id"])
        assert list(publication.contributors.values_list("id", flat=True)) == [priya.id]

    def test_update_replaces_and_empty_list_clears(self, admin, org, priya, ada, ready):
        publication = _publication(admin, org, ready, authors=["Old Name"])

        result = run(
            UPDATE,
            ctx(admin, org),
            {"input": {"id": str(publication.id), "contributorIds": [str(ada.id)]}},
        )
        payload = result.data["updatePublication"]
        assert payload["success"] is True, payload
        assert _ids(payload["data"]["contributors"]) == [ada.id]
        assert payload["data"]["authors"] == []

        result = run(
            UPDATE, ctx(admin, org), {"input": {"id": str(publication.id), "contributorIds": []}}
        )
        assert result.data["updatePublication"]["data"]["contributors"] == []

    @pytest.mark.parametrize("sent", [{}, {"contributorIds": None}])
    def test_update_without_ids_keeps_contributors_and_names(self, admin, org, priya, ready, sent):
        publication = _publication(admin, org, ready, authors=["Old Name"])
        publication.contributors.add(priya)

        result = run(
            UPDATE,
            ctx(admin, org),
            {"input": {"id": str(publication.id), "title": "New", **sent}},
        )

        payload = result.data["updatePublication"]
        assert payload["success"] is True, payload
        assert _ids(payload["data"]["contributors"]) == [priya.id]
        assert payload["data"]["authors"] == ["Old Name"]

    @pytest.mark.parametrize("bad_id", ["999999", "not-a-number"])
    def test_unknown_user_id_saves_nothing(self, admin, org, priya, ready, bad_id):
        publication = _publication(admin, org, ready)
        publication.contributors.add(priya)

        result = run(
            UPDATE,
            ctx(admin, org),
            {"input": {"id": str(publication.id), "title": "Changed", "contributorIds": [bad_id]}},
        )

        payload = result.data["updatePublication"]
        assert payload["success"] is False
        assert "contributors" in _field_errors(payload)
        publication.refresh_from_db()
        assert publication.title == "Water report"
        assert list(publication.contributors.all()) == [priya]

    def test_non_member_cannot_change_contributors(self, admin, org, outsider, ready):
        publication = _publication(admin, org, ready)

        result = run(
            UPDATE,
            ctx(outsider),
            {"input": {"id": str(publication.id), "contributorIds": [str(outsider.id)]}},
        )

        assert result.data["updatePublication"]["success"] is False
        assert publication.contributors.count() == 0


# --------------------------------------------------------------------------- #
# Publishing
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestPublishNeedsPeople:
    def test_contributor_alone_is_enough(self, admin, org, priya, ready):
        publication = _publication(admin, org, ready)
        publication.contributors.add(priya)

        result = run(PUBLISH, ctx(admin, org), {"id": str(publication.id)})

        assert result.data["publishPublication"]["success"] is True

    def test_old_names_alone_still_publish(self, admin, org, ready):
        publication = _publication(admin, org, ready, authors=["Old Name"])

        result = run(PUBLISH, ctx(admin, org), {"id": str(publication.id)})

        assert result.data["publishPublication"]["success"] is True

    def test_no_people_is_refused_under_the_authors_key(self, admin, org, ready):
        publication = _publication(admin, org, ready)

        result = run(PUBLISH, ctx(admin, org), {"id": str(publication.id)})

        payload = result.data["publishPublication"]
        assert payload["success"] is False
        assert _field_errors(payload) == {"authors"}

    def test_published_cannot_lose_its_last_contributor(self, admin, org, priya, ready):
        publication = _publication(admin, org, ready, status=PublicationStatus.PUBLISHED)
        publication.contributors.add(priya)

        result = run(
            UPDATE, ctx(admin, org), {"input": {"id": str(publication.id), "contributorIds": []}}
        )

        assert result.data["updatePublication"]["success"] is False
        assert list(publication.contributors.all()) == [priya]


# --------------------------------------------------------------------------- #
# Reading contributors
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestReadContributors:
    def test_anonymous_sees_contributors_without_emails(self, admin, org, priya, ada, ready):
        publication = _publication(admin, org, ready, status=PublicationStatus.PUBLISHED)
        publication.contributors.add(priya, ada)

        result = run(GET, ctx(AnonymousUser()), {"id": str(publication.id)})

        assert result.errors is None, result.errors
        rows = result.data["getPublication"]["contributors"]
        assert {row["fullName"] for row in rows} == {"Priya Sharma", "ada_k"}
        assert {row["email"] for row in rows} == {""}
        priya.refresh_from_db()
        assert priya.email == "priya@x.org"

    def test_editor_sees_emails(self, admin, org, priya, ready):
        publication = _publication(admin, org, ready)
        publication.contributors.add(priya)

        result = run(GET, ctx(admin, org), {"id": str(publication.id)})

        assert result.data["getPublication"]["contributors"][0]["email"] == "priya@x.org"


# --------------------------------------------------------------------------- #
# Matching saved names to users
# --------------------------------------------------------------------------- #
class TestMatching:
    def test_display_name_follows_full_name_rule(self):
        assert display_name("Priya", "Sharma", "priya_s") == "Priya Sharma"
        assert display_name("Priya", "", "priya_s") == "Priya"
        assert display_name("", "Sharma", "priya_s") == "Sharma"
        assert display_name("", "", "ada_k") == "ada_k"

    def test_case_and_spaces_are_ignored(self):
        index = index_users([(1, "Priya", "Sharma", "p")])
        assert match_author("  priya   SHARMA ", index, None, set()) == 1

    def test_shared_name_never_guesses(self):
        index = index_users([(1, "Rahul", "Verma", "r1"), (2, "Rahul", "Verma", "r2")])
        assert match_author("Rahul Verma", index, None, set()) is None
        assert match_author("Rahul Verma", index, None, {1, 2}) is None

    def test_shared_name_prefers_owner_then_single_member(self):
        index = index_users([(1, "Rahul", "Verma", "r1"), (2, "Rahul", "Verma", "r2")])
        assert match_author("Rahul Verma", index, 2, {1}) == 2
        assert match_author("Rahul Verma", index, 99, {1}) == 1

    def test_split_links_once_and_reports_the_rest(self):
        index = index_users([(1, "Priya", "Sharma", "p"), (2, "", "", "ada_k")])
        linked, unlinked = split_authors(
            ["Priya Sharma", "Priya Sharma", "ada_k", "Journey Bot", " "], index, None, set()
        )
        assert linked == [1, 2]
        assert unlinked == ["Journey Bot"]


@pytest.mark.django_db
class TestExistingData:
    def test_migration_links_matches_and_keeps_names(self, admin, org, priya, ada, ready, capsys):
        publication = _publication(
            admin, org, ready, authors=["Priya Sharma", "Priya Sharma", "ada_k", "Journey Bot"]
        )

        link_migration.link_contributors(django_apps, None)

        assert sorted(publication.contributors.values_list("id", flat=True)) == sorted(
            [priya.id, ada.id]
        )
        publication.refresh_from_db()
        assert publication.authors == ["Priya Sharma", "Priya Sharma", "ada_k", "Journey Bot"]
        output = capsys.readouterr().out
        assert "2 linked, 1 names not linked" in output
        assert "Journey Bot" not in output  # deploy logs are public

    def test_command_lists_only_unlinked_names(self, admin, org, priya, ready):
        _publication(admin, org, ready, authors=["Priya Sharma"])
        unmatched = _publication(admin, org, ready, authors=["Priya Sharma", "Journey Bot"])

        out = io.StringIO()
        call_command("unlinked_publication_authors", stdout=out)

        lines = out.getvalue().strip().splitlines()
        assert len(lines) == 2
        assert str(unmatched.id) in lines[0] and "['Journey Bot']" in lines[0]
        assert lines[1] == "1 publication(s) with unlinked author names"
