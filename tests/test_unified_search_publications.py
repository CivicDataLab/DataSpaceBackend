"""Publications in unified search.

Root cause: ``UnifiedSearchResultSerializer`` requires ``tags`` on every result,
publication search documents have no ``tags`` field, and ``_normalize_result``
filled defaults only for events and publishers. Any unified search page holding
a publication failed with 500: always with ``types=publication``, and with all
types as soon as a publication ranked onto the page (e.g. searching "publish").

Fix: ``_normalize_result`` gives publication hits an empty ``tags`` list (and
empty title/description when missing), the same way events get them.
"""

import types

import pytest

from api.models import Publication
from api.utils.enums import PublicationStatus
from api.views.search_unified import UnifiedSearch, UnifiedSearchResultSerializer
from authorization.models import User
from search.documents.publication_document import PublicationDocument


def hit(source: dict, index: str) -> types.SimpleNamespace:
    """Stand-in for an Elasticsearch hit: ``to_dict()`` and ``meta``."""
    return types.SimpleNamespace(
        to_dict=lambda: dict(source),
        meta=types.SimpleNamespace(score=1.0, index=index),
    )


def serialize(*hits: types.SimpleNamespace) -> list:
    view = UnifiedSearch()
    results = [view._normalize_result(h) for h in hits]
    return list(UnifiedSearchResultSerializer(results, many=True).data)


@pytest.fixture
def publication(db) -> Publication:
    owner = User.objects.create(username="owner", keycloak_id="owner")
    return Publication.objects.create(
        title="Budget Brief", user=owner, status=PublicationStatus.PUBLISHED
    )


def indexed(publication: Publication) -> dict:
    """The document as stored in the index (empty values dropped, as ES returns it)."""
    source = PublicationDocument().prepare(publication)
    source["id"] = str(publication.id)
    return {key: value for key, value in source.items() if value not in (None, "", [], {})}


def test_publication_result_serializes_with_its_link(publication) -> None:
    [result] = serialize(hit(indexed(publication), "publication"))
    assert result["type"] == "publication"
    assert result["title"] == "Budget Brief"
    assert result["url_slug"] == publication.url_slug
    assert result["tags"] == []


def test_publication_without_title_or_description_serializes(publication) -> None:
    source = indexed(publication)
    source.pop("title", None)
    source.pop("description", None)
    [result] = serialize(hit(source, "publication"))
    assert (result["title"], result["description"]) == ("", "")


def test_mixed_page_with_a_publication_serializes(publication) -> None:
    dataset = {"id": "d1", "title": "Rainfall", "description": "", "status": "PUBLISHED"}
    dataset["tags"] = ["rain"]
    results = serialize(hit(dataset, "dataset"), hit(indexed(publication), "publication"))
    assert [r["type"] for r in results] == ["dataset", "publication"]
    assert results[0]["tags"] == ["rain"]
