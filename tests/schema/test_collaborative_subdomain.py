"""Collaborative slugs that cannot work as a subdomain (#292).

Root cause: the slug is the collaborative's subdomain (`<slug>.<domain>`), but
the backend allowed 75 characters while a DNS label holds at most 63, and it
accepted names the frontend's routing reserves (www, api, admin, ...). Such a
collaborative saved fine and its address never opened.

Fix: `subdomain_error` in api/models/Collaborative.py refuses a new slug that is
too long or reserved; a slug made from the title is cut to 63 characters and gets
the random suffix when it is reserved, like when it is taken. Slugs that already
exist are not checked again, so those collaboratives can still be edited.
"""

import types

import pytest
from django.test import RequestFactory

from api.models import Collaborative
from api.models.Collaborative import RESERVED_SUBDOMAINS, SUBDOMAIN_MAX_LENGTH
from api.schema.schema import schema
from authorization.models import User

UPDATE = "mutation($d: CollaborativeInputPartial!){ updateCollaborative(data:$d){ id slug } }"


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


def messages(result):
    return [error.message for error in result.errors or []]


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", email="o@example.org", keycloak_id="owner")


@pytest.fixture
def collaborative(owner):
    return Collaborative.objects.create(title="Health data", user=owner)


def update_slug(owner, collaborative, slug):
    return run(owner, UPDATE, d={"id": str(collaborative.id), "slug": slug})


# ─── A typed slug ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("slug", ["www", "api", "admin", "staging", "cdn"])
def test_reserved_slug_is_refused(owner, collaborative, slug):
    result = update_slug(owner, collaborative, slug)

    assert messages(result) == ["This subdomain is reserved. Choose another."]
    collaborative.refresh_from_db()
    assert collaborative.slug == "health-data"


def test_slug_longer_than_a_dns_label_is_refused(owner, collaborative):
    result = update_slug(owner, collaborative, "a" * (SUBDOMAIN_MAX_LENGTH + 1))

    assert messages(result) == ["Slug cannot be longer than 63 characters."]
    collaborative.refresh_from_db()
    assert collaborative.slug == "health-data"


def test_slug_of_63_characters_is_accepted(owner, collaborative):
    slug = "a" * SUBDOMAIN_MAX_LENGTH

    result = update_slug(owner, collaborative, slug)

    assert result.errors is None
    assert result.data["updateCollaborative"]["slug"] == slug


def test_name_that_only_contains_a_reserved_word_is_accepted(owner, collaborative):
    result = update_slug(owner, collaborative, "admin-tools")

    assert result.errors is None
    assert result.data["updateCollaborative"]["slug"] == "admin-tools"


def test_existing_long_slug_does_not_block_other_edits(owner, owner_old_collaborative):
    result = run(
        owner,
        UPDATE,
        d={
            "id": str(owner_old_collaborative.id),
            "slug": owner_old_collaborative.slug,
            "title": "New title",
        },
    )

    assert result.errors is None
    owner_old_collaborative.refresh_from_db()
    assert owner_old_collaborative.title == "New title"
    assert len(owner_old_collaborative.slug) == 70


@pytest.fixture
def owner_old_collaborative(owner):
    """A collaborative saved before the limit, with a 70-character slug."""
    collaborative = Collaborative.objects.create(title="Old", user=owner)
    Collaborative.objects.filter(pk=collaborative.pk).update(slug="o" * 70)
    collaborative.refresh_from_db()
    return collaborative


# ─── A slug made from the title ───────────────────────────────────────────────


def test_slug_from_a_long_title_fits_a_dns_label(owner):
    collaborative = Collaborative.objects.create(title="word " * 40, user=owner)

    assert len(collaborative.slug) <= SUBDOMAIN_MAX_LENGTH


def test_slug_from_a_long_taken_title_fits_a_dns_label(owner):
    Collaborative.objects.create(title="word " * 40, user=owner)
    second = Collaborative.objects.create(title="word " * 40, user=owner)

    assert len(second.slug) <= SUBDOMAIN_MAX_LENGTH


@pytest.mark.parametrize("title", ["Admin", "WWW", "API"])
def test_slug_from_a_reserved_title_gets_a_suffix(owner, title):
    collaborative = Collaborative.objects.create(title=title, user=owner)

    assert collaborative.slug not in RESERVED_SUBDOMAINS
    assert collaborative.slug.startswith(f"{title.lower()}-")
