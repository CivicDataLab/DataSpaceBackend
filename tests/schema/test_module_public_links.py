import types

import pytest
from django.contrib.auth.models import AnonymousUser

from api.models import AIModel, Collaborative, Publication, UseCase
from api.schema.schema import schema
from api.utils.enums import CollaborativeStatus, PublicationStatus, UseCaseStatus
from authorization.models import User


def run(query, variables, user=None):
    ctx = types.SimpleNamespace(user=user or AnonymousUser(), context={})
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", keycloak_id="owner")


def make_model(owner, **kw):
    data = dict(
        name="sarvam-translate",
        display_name="Sarvam Translate",
        description="d",
        model_type="TRANSLATION",
        provider="OPENAI",
        user=owner,
    )
    data.update(kw)
    return AIModel.objects.create(**data)


# --- every module: id, link, same title twice, rename keeps id ---------------


@pytest.mark.parametrize("kind", ["usecase", "collaborative", "publication", "aimodel"])
def test_ids_links_and_duplicate_titles(kind, owner) -> None:
    def make(title):
        if kind == "usecase":
            return UseCase.objects.create(title=title, user=owner)
        if kind == "collaborative":
            return Collaborative.objects.create(title=title, user=owner)
        if kind == "publication":
            return Publication.objects.create(title=title, user=owner)
        return make_model(owner, display_name=title, name=f"m-{AIModel.objects.count()}")

    a = make("Air Quality Study")
    b = make("Air Quality Study")
    assert len(a.public_id) == 12 and a.public_id != b.public_id
    assert a.url_slug == f"air-quality-study-{a.public_id}"
    assert a.url_slug != b.url_slug

    old = a.public_id
    if kind == "aimodel":
        a.display_name = "Air Quality Study v2"
    else:
        a.title = "Air Quality Study v2"
    a.save()
    a.refresh_from_db()
    assert a.public_id == old
    assert a.url_slug == f"air-quality-study-v2-{old}"


def test_long_collaborative_title_saves(owner) -> None:
    # full_clean checks slug length and format; the cut must not leave a trailing hyphen.
    title = "District wise monthly rainfall and temperature readings for all states 1990"
    c = Collaborative.objects.create(title=title, user=owner)
    assert len(c.slug) <= 75 and not c.slug.endswith("-")


# --- use cases -----------------------------------------------------------------

UC = "query($s: String!) { useCaseBySlug(slug: $s) { id publicId urlSlug } }"


def test_use_case_by_link(owner) -> None:
    uc = UseCase.objects.create(title="Flood Maps", user=owner, status=UseCaseStatus.PUBLISHED)
    for value in [uc.url_slug, uc.public_id, f"old-words-{uc.public_id}"]:
        res = run(UC, {"s": value})
        assert res.errors is None, res.errors
        assert res.data["useCaseBySlug"]["id"] == str(uc.id)
        assert res.data["useCaseBySlug"]["urlSlug"] == uc.url_slug


def test_use_case_by_link_hides_drafts_and_plain_words(owner) -> None:
    draft = UseCase.objects.create(title="Secret", user=owner)
    pub = UseCase.objects.create(title="Open One", user=owner, status=UseCaseStatus.PUBLISHED)
    for value in [draft.url_slug, pub.slug, "aaaaaaaaaaaa", str(pub.id)]:
        res = run(UC, {"s": value})
        assert res.errors is None, res.errors
        assert res.data["useCaseBySlug"] is None


# --- collaboratives ------------------------------------------------------------

CB = "query($s: String!) { collaborativeBySlug(slug: $s) { id publicId urlSlug } }"


def test_collaborative_by_link_and_old_slug(owner) -> None:
    c = Collaborative.objects.create(
        title="Clean Rivers", user=owner, status=CollaborativeStatus.PUBLISHED
    )
    for value in [c.url_slug, c.public_id, f"old-words-{c.public_id}", c.slug]:
        res = run(CB, {"s": value})
        assert res.errors is None, res.errors
        assert res.data["collaborativeBySlug"]["id"] == str(c.id)


def test_collaborative_old_slug_with_duplicates_gives_oldest(owner) -> None:
    first = Collaborative.objects.create(title="Clean Rivers", user=owner)
    Collaborative.objects.create(title="Clean Rivers", user=owner)
    res = run(CB, {"s": "clean-rivers"})
    assert res.data["collaborativeBySlug"]["id"] == str(first.id)


def test_collaborative_unknown_link_errors(owner) -> None:
    res = run(CB, {"s": "nothing-aaaaaaaaaaaa"})
    assert res.errors


# --- publications --------------------------------------------------------------

PB = """query($id: UUID, $p: String) {
  getPublication(publicationId: $id, publicId: $p) { id publicId urlSlug }
}"""


def test_publication_by_public_id(owner) -> None:
    p = Publication.objects.create(
        title="Budget Brief", user=owner, status=PublicationStatus.PUBLISHED
    )
    for value in [p.url_slug, p.public_id]:
        res = run(PB, {"p": value})
        assert res.errors is None, res.errors
        assert res.data["getPublication"]["id"] == str(p.id)
    res = run(PB, {"id": str(p.id)})
    assert res.data["getPublication"]["publicId"] == p.public_id


def test_publication_draft_by_public_id(owner) -> None:
    p = Publication.objects.create(title="Draft Brief", user=owner)
    assert run(PB, {"p": p.public_id}).errors  # anonymous refused
    stranger = User.objects.create(username="s", keycloak_id="s")
    assert run(PB, {"p": p.public_id}, stranger).errors
    res = run(PB, {"p": p.public_id}, owner)
    assert res.errors is None and res.data["getPublication"]["id"] == str(p.id)


def test_publication_unknown_gives_null(owner) -> None:
    for value in ["aaaaaaaaaaaa", "no-id-here"]:
        res = run(PB, {"p": value})
        assert res.errors is None, res.errors
        assert res.data["getPublication"] is None


# --- AI models -----------------------------------------------------------------

AM = """query($id: Int, $p: String) {
  getAiModel(modelId: $id, publicId: $p) { id publicId urlSlug }
}"""


def test_ai_model_by_public_id(owner) -> None:
    m = make_model(owner, is_public=True, is_active=True)
    for value in [m.url_slug, m.public_id]:
        res = run(AM, {"p": value})
        assert res.errors is None, res.errors
        assert res.data["getAiModel"]["id"] == m.id
    assert run(AM, {"id": m.id}).data["getAiModel"]["publicId"] == m.public_id


def test_ai_model_private_and_unknown(owner) -> None:
    m = make_model(owner, is_public=False, is_active=True)
    assert run(AM, {"p": m.public_id}).data["getAiModel"] is None
    assert run(AM, {"p": m.public_id}, owner).data["getAiModel"]["id"] == m.id
    assert run(AM, {"p": "aaaaaaaaaaaa"}).data["getAiModel"] is None
    assert run(AM, {"p": "words-only"}).data["getAiModel"] is None
