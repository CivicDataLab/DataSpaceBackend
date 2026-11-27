"""SDG filter and facet in search (follow-up to CivicDataLab/DataSpaceFrontend#543).

Root cause: use cases and collaboratives carry SDGs, but no search document
indexed them, and unified search had no ``sdgs`` filter. The frontend's SDG
links (``/search?sdgs=...&types=usecase|collaborative``) were ignored and showed
every item. The per-type views sent an unknown ``sdgs`` filter to the metadata
branch, so they matched nothing.

Fix: both documents index SDG codes ("SDG3") as a keyword field. Unified search
filters on ``sdgs`` and returns an ``sdgs`` facet; the use case and collaborative
views filter on it too. Codes only: two SDG names contain commas and filter
values are split on commas. Migration 0066 puts the field on live indexes before
the deploy refills them.
"""

import importlib
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings
from elasticsearch_dsl import Search

from api.models import SDG, Collaborative, UseCase
from api.utils.search_query import sdg_codes
from api.views.search_collaborative import SearchCollaborative
from api.views.search_unified import UnifiedSearch
from api.views.search_usecase import SearchUseCase
from authorization.models import User
from search.documents.collaborative_document import CollaborativeDocument
from search.documents.usecase_document import UseCaseDocument

migration = importlib.import_module("api.migrations.0066_usecase_collaborative_search_sdgs")

DOCUMENTS = [UseCaseDocument, CollaborativeDocument]


@pytest.fixture
def user(db):
    return User.objects.create(username="author", keycloak_id="author")


@pytest.fixture
def goals(db):
    return [
        SDG.objects.create(
            name="Industry, Innovation and Infrastructure", code="SDG9", number=9, slug="sdg9"
        ),
        SDG.objects.create(name="Good Health and Well-being", code="SDG3", number=3, slug="sdg3"),
    ]


@pytest.fixture
def use_case(user, goals):
    use_case = UseCase.objects.create(title="Clinic finder", summary="<p>s</p>", user=user)
    use_case.sdgs.add(*goals)
    return use_case


@pytest.fixture
def collaborative(user, goals):
    collaborative = Collaborative.objects.create(title="Health data", summary="s", user=user)
    collaborative.sdgs.add(*goals)
    return collaborative


def _filters(search):
    return search.to_dict().get("query", {}).get("bool", {}).get("filter", [])


# Documents


@pytest.mark.parametrize("document", DOCUMENTS)
def test_sdgs_are_an_exact_keyword_field(document):
    mapping = document._doc_type.mapping.to_dict()["properties"]["sdgs"]

    assert mapping == {"type": "keyword"}


def test_use_case_indexes_sdg_codes_in_goal_order(use_case):
    assert UseCaseDocument().prepare(use_case)["sdgs"] == ["SDG3", "SDG9"]


def test_collaborative_indexes_sdg_codes_in_goal_order(collaborative):
    assert CollaborativeDocument().prepare(collaborative)["sdgs"] == ["SDG3", "SDG9"]


def test_item_without_sdgs_indexes_an_empty_list(user):
    use_case = UseCase.objects.create(title="No goals", summary="<p>s</p>", user=user)

    assert UseCaseDocument().prepare(use_case)["sdgs"] == []


@pytest.mark.parametrize("document", DOCUMENTS)
def test_changing_an_sdg_reindexes_its_items(document):
    assert SDG in document.Django.related_models


def test_changing_an_sdg_finds_its_use_cases_and_collaboratives(use_case, collaborative, goals):
    assert UseCaseDocument().get_instances_from_related(goals[0]) == [use_case]
    assert CollaborativeDocument().get_instances_from_related(goals[0]) == [collaborative]


# Filter values


@pytest.mark.parametrize(
    "value,expected",
    [
        ("SDG3", ["SDG3"]),
        ("sdg3, SDG9", ["SDG3", "SDG9"]),
        (" , ", []),
        ("", []),
    ],
)
def test_sdg_codes_ignore_case_spaces_and_empty_parts(value, expected):
    assert sdg_codes(value) == expected


# Unified search


def test_unified_search_filters_on_sdg_codes():
    search = UnifiedSearch()._apply_filters(Search(), {"sdgs": "sdg3,SDG9"})

    assert {"terms": {"sdgs": ["SDG3", "SDG9"]}} in _filters(search)


def test_unified_search_ignores_an_empty_sdgs_value():
    search = UnifiedSearch()._apply_filters(Search(), {"sdgs": ""})

    assert _filters(search) == []


def _unified_search(aggregations):
    response = mock.MagicMock()
    response.__iter__.return_value = iter([])
    response.aggregations.to_dict.return_value = aggregations
    response.hits.total.value = 0
    sent = []

    def execute(search):
        sent.append(search.to_dict())
        return response

    with mock.patch.object(Search, "execute", autospec=True, side_effect=execute):
        _, _, result = UnifiedSearch().perform_unified_search(
            "", {}, ["usecase", "collaborative"], 1, 10
        )
    return sent[0], result


def test_unified_search_asks_for_an_sdgs_facet():
    body, _ = _unified_search({})

    assert body["aggs"]["sdgs"] == {"terms": {"field": "sdgs", "size": 50}}


def test_unified_search_returns_the_sdgs_facet_like_sectors():
    buckets = {"buckets": [{"key": "SDG3", "doc_count": 2}, {"key": "SDG9", "doc_count": 1}]}

    _, aggregations = _unified_search({"sdgs": buckets})

    assert aggregations["sdgs"] == {"SDG3": 2, "SDG9": 1}


# Per-type search


@pytest.mark.django_db
@pytest.mark.parametrize("view", [SearchUseCase, SearchCollaborative])
def test_per_type_search_filters_on_sdg_codes(view):
    cache.clear()

    search = view().add_filters({"sdgs": "SDG3,sdg9"}, Search())

    assert _filters(search) == [{"terms": {"sdgs": ["SDG3", "SDG9"]}}]


# Migration 0066

NAMES = {
    "search.documents.usecase_document": "usecase",
    "search.documents.collaborative_document": "collaborative",
}


def _migrate(existing, put_mapping_error=None):
    es = mock.MagicMock()
    es.options.return_value = es
    es.indices.exists.side_effect = lambda index: index in existing
    if put_mapping_error:
        es.indices.put_mapping.side_effect = put_mapping_error
    with (
        override_settings(ELASTICSEARCH_INDEX_NAMES=NAMES),
        mock.patch("elasticsearch_dsl.connections.connections.get_connection", return_value=es),
    ):
        migration.add_sdgs_field(None, None)
    return es


def test_migration_adds_the_keyword_field_to_live_indexes():
    es = _migrate({"usecase", "collaborative"})

    assert es.indices.put_mapping.call_args_list == [
        mock.call(index="usecase", properties={"sdgs": {"type": "keyword"}}),
        mock.call(index="collaborative", properties={"sdgs": {"type": "keyword"}}),
    ]


def test_migration_skips_a_missing_index():
    es = _migrate({"collaborative"})

    es.indices.put_mapping.assert_called_once_with(
        index="collaborative", properties={"sdgs": {"type": "keyword"}}
    )


def test_migration_never_fails_and_still_tries_every_index():
    es = _migrate({"usecase", "collaborative"}, put_mapping_error=RuntimeError("conflict"))

    assert es.indices.put_mapping.call_count == 2
