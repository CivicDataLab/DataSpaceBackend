"""Use case dashboard links must be on an allowed host (#216).

Root cause: `addUsecaseDashboard`, `addUsecaseDashboards` and
`updateUsecaseDashboard` stored any link, and the host check that decides what
the public use case page may embed existed only in the frontend, so the API
saved links to any site.

Fix: `api/utils/dashboard_links.py` accepts only https links (default port, no
credentials) whose host is in `settings.DASHBOARD_EMBED_ORIGINS` or a subdomain
of one. All three mutations refuse other links with `success: false` and save
nothing; dashboards expose `embedUrl` (null for a link that may not be embedded,
e.g. one saved before this check); `checkDashboardLink` runs the same check for
the builder while the user types.
"""

import types

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings

from api.models import UseCase, UseCaseDashboard
from api.schema.schema import schema
from api.utils.dashboard_links import (
    NOT_ALLOWED_MESSAGE,
    DashboardLinkError,
    clean_dashboard_link,
    embed_url,
)
from api.utils.enums import UseCaseStatus
from authorization.models import User

ORIGINS = ["analytics.civicdataspace.in", "justicehub.in", "public.tableau.com"]

pytestmark = pytest.mark.usefixtures("origins")


@pytest.fixture
def origins():
    with override_settings(DASHBOARD_EMBED_ORIGINS=ORIGINS):
        yield


REFUSED = [
    "https://evil.example/dash",
    "http://justicehub.in/dash",  # not https
    "https://justicehub.in:8443/dash",  # other port
    "https://justicehub.in:abc/dash",  # broken port
    "https://user:pw@justicehub.in/dash",  # credentials
    "https://justicehub.in@evil.example/dash",
    "https://evil.example\\@justicehub.in/dash",  # browsers read \ as /
    "https://evil-justicehub.in/dash",  # look-alike
    "https://justicehub.in.evil.example/dash",
    "https://evil.example%2f.justicehub.in/dash",
    "https://justicehub.in/da sh",
    "javascript:alert(1)",
    "ftp://justicehub.in/dash",
    "https://",
    "https://justicehub.in/" + "a" * 200,  # longer than the column
]

ALLOWED = [
    ("https://justicehub.in/dash", "https://justicehub.in/dash"),
    ("justicehub.in/dash", "https://justicehub.in/dash"),  # scheme added, like the frontend
    (
        "  https://public.tableau.com/views/x?:embed=y  ",
        "https://public.tableau.com/views/x?:embed=y",
    ),
    (
        "https://dev.analytics.civicdataspace.in/superset/1",
        "https://dev.analytics.civicdataspace.in/superset/1",
    ),
    ("https://JusticeHub.in:443/dash", "https://JusticeHub.in:443/dash"),
]


# --- the check ----------------------------------------------------------------


@pytest.mark.parametrize("link", REFUSED)
def test_refused_links(link):
    with pytest.raises(DashboardLinkError):
        clean_dashboard_link(link)
    assert embed_url(link) is None


@pytest.mark.parametrize("link,stored", ALLOWED)
def test_allowed_links(link, stored):
    assert clean_dashboard_link(link) == stored
    assert embed_url(link) == stored


@pytest.mark.parametrize("link", [None, "", "   "])
def test_empty_link_is_kept_empty(link):
    assert clean_dashboard_link(link) == ""
    assert embed_url(link) is None


def test_hosts_come_from_the_setting():
    with override_settings(DASHBOARD_EMBED_ORIGINS=["example.org"]):
        assert clean_dashboard_link("https://sub.example.org/x") == "https://sub.example.org/x"
        with pytest.raises(DashboardLinkError):
            clean_dashboard_link("https://justicehub.in/x")


def test_empty_setting_allows_nothing():
    with override_settings(DASHBOARD_EMBED_ORIGINS=[""]):
        with pytest.raises(DashboardLinkError):
            clean_dashboard_link("https://justicehub.in/x")


# --- the mutations --------------------------------------------------------------

SELECTION = "{ success errors { nonFieldErrors } data { id link embedUrl } }"


def run(user, query, **variables):
    ctx = types.SimpleNamespace(user=user, context={}, request=None, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def w(db):
    owner = User.objects.create(username="owner", keycloak_id="owner")
    usecase = UseCase.objects.create(title="uc", user=owner, status=UseCaseStatus.DRAFT)
    return types.SimpleNamespace(owner=owner, usecase=usecase)


def add_one(w, link):
    return run(
        w.owner,
        f'mutation ($u: Int!, $l: String) {{ addUsecaseDashboard(usecaseId: $u, name: "d", '
        f"link: $l) {SELECTION} }}",
        u=w.usecase.id,
        l=link,
    ).data["addUsecaseDashboard"]


def assert_refused(result):
    assert result["success"] is False
    assert result["errors"]["nonFieldErrors"] == [NOT_ALLOWED_MESSAGE]


@pytest.mark.parametrize("link", ["https://evil.example/d", "http://justicehub.in/d"])
def test_add_refuses_and_saves_nothing(w, link):
    assert_refused(add_one(w, link))
    assert not UseCaseDashboard.objects.exists()


def test_add_saves_the_cleaned_link(w):
    result = add_one(w, " justicehub.in/d ")
    assert result["success"] is True, result
    assert result["data"]["link"] == "https://justicehub.in/d"
    assert result["data"]["embedUrl"] == "https://justicehub.in/d"
    assert UseCaseDashboard.objects.get().link == "https://justicehub.in/d"


def test_add_without_a_link_still_works(w):
    result = add_one(w, None)
    assert result["success"] is True, result
    assert result["data"]["embedUrl"] is None


BATCH = """
mutation ($u: Int!, $a: String!, $b: String!) {
  addUsecaseDashboards(input: {usecaseId: $u, dashboards: [
    {name: "a", link: $a}, {name: "b", link: $b}
  ]}) { success errors { nonFieldErrors } data { link } }
}
"""


def test_batch_with_one_refused_link_saves_none(w):
    result = run(
        w.owner, BATCH, u=w.usecase.id, a="https://justicehub.in/a", b="https://evil.example/b"
    ).data["addUsecaseDashboards"]
    assert_refused(result)
    assert not UseCaseDashboard.objects.exists()


def test_batch_of_allowed_links_saves_all(w):
    result = run(
        w.owner, BATCH, u=w.usecase.id, a="justicehub.in/a", b="https://public.tableau.com/b"
    ).data["addUsecaseDashboards"]
    assert result["success"] is True, result
    assert [d["link"] for d in result["data"]] == [
        "https://justicehub.in/a",
        "https://public.tableau.com/b",
    ]


UPDATE = (
    'mutation ($id: String!, $l: String) { updateUsecaseDashboard(id: $id, name: "new", '
    f"link: $l) {SELECTION} }}"
)


@pytest.fixture
def saved(w):
    return UseCaseDashboard.objects.create(
        name="old", link="https://justicehub.in/old", usecase=w.usecase
    )


def test_update_refuses_and_keeps_the_old_link_and_name(w, saved):
    result = run(w.owner, UPDATE, id=str(saved.id), l="https://evil.example/x").data[
        "updateUsecaseDashboard"
    ]
    assert_refused(result)
    saved.refresh_from_db()
    assert (saved.name, saved.link) == ("old", "https://justicehub.in/old")


def test_update_saves_an_allowed_link(w, saved):
    result = run(w.owner, UPDATE, id=str(saved.id), l="public.tableau.com/x").data[
        "updateUsecaseDashboard"
    ]
    assert result["success"] is True, result
    saved.refresh_from_db()
    assert saved.link == "https://public.tableau.com/x"


def test_update_without_a_link_keeps_it(w, saved):
    result = run(w.owner, UPDATE, id=str(saved.id), l=None).data["updateUsecaseDashboard"]
    assert result["success"] is True, result
    saved.refresh_from_db()
    assert (saved.name, saved.link) == ("new", "https://justicehub.in/old")


# --- reading --------------------------------------------------------------------


def test_links_saved_before_the_check_are_not_embedded(w):
    """Old rows are left as they are; only embedUrl hides them."""
    UseCaseDashboard.objects.create(name="old", link="https://evil.example/x", usecase=w.usecase)
    UseCaseDashboard.objects.create(name="ok", link="https://justicehub.in/x", usecase=w.usecase)

    result = run(
        w.owner,
        "query ($u: Int!) { usecaseDashboards(usecaseId: $u) { name link embedUrl } }",
        u=w.usecase.id,
    )
    assert result.errors is None, result.errors
    assert result.data["usecaseDashboards"] == [
        {"name": "old", "link": "https://evil.example/x", "embedUrl": None},
        {"name": "ok", "link": "https://justicehub.in/x", "embedUrl": "https://justicehub.in/x"},
    ]


# --- checkDashboardLink -----------------------------------------------------------

CHECK = "query ($l: String!) { checkDashboardLink(link: $l) { allowed embedUrl message } }"


def test_check_allowed_link(w):
    result = run(w.owner, CHECK, l="justicehub.in/x")
    assert result.errors is None, result.errors
    assert result.data["checkDashboardLink"] == {
        "allowed": True,
        "embedUrl": "https://justicehub.in/x",
        "message": None,
    }


def test_check_refused_link(w):
    result = run(w.owner, CHECK, l="https://evil.example/x")
    assert result.data["checkDashboardLink"] == {
        "allowed": False,
        "embedUrl": None,
        "message": NOT_ALLOWED_MESSAGE,
    }
    assert not UseCaseDashboard.objects.exists()


def test_check_needs_sign_in(db):
    result = run(AnonymousUser(), CHECK, l="justicehub.in/x")
    assert result.errors
    assert result.data is None
