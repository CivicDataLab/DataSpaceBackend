"""Layer 3: the search endpoint's order and fallbacks, helpers mocked (SEARCH1)."""

from typing import Any, Iterator
from unittest import mock

import pytest
from rest_framework.test import APIRequestFactory

from api.services.query_engine.errors import SearchUnavailable
from api.services.query_engine.scope import ResolvedScope
from api.views.query_engine.search_view import SearchView

VIEW = "api.views.query_engine.search_view"
NAMES = [
    "resolve_scope",
    "scope_has_no_datasets",
    "embed_question",
    "build_search_filters",
    "hybrid_search",
    "keep_hits_in_scope",
    "rerank_hits",
    "group_by_dataset",
    "judge_weak_match",
    "search_response",
]


@pytest.fixture
def helpers() -> Iterator[mock.MagicMock]:
    calls = mock.MagicMock()
    calls.resolve_scope.return_value = ResolvedScope(kind="platform")
    calls.scope_has_no_datasets.return_value = False
    calls.embed_question.return_value = ([0.1], [])
    calls.hybrid_search.return_value = (["hit"], True)
    calls.keep_hits_in_scope.return_value = (["hit"], {}, {})
    calls.rerank_hits.return_value = (["hit"], True)
    calls.search_response.return_value = {"results": []}
    with mock.patch.multiple(VIEW, **{name: getattr(calls, name) for name in NAMES}), mock.patch(
        "api.views.query_engine.base.InternalQeView.authentication_classes", []
    ), mock.patch("api.views.query_engine.base.InternalQeView.permission_classes", []):
        yield calls


def post(body: Any = None) -> Any:
    request = APIRequestFactory().post(
        "/api/internal/qe/search/", body or {"scope": "platform", "query": "anaemia"}, format="json"
    )
    return SearchView.as_view()(request)


def order(calls: mock.MagicMock) -> list:
    return [name for name, _, _ in calls.mock_calls if "." not in name]


def test_filters_in_the_database_before_reranking_and_grouping(helpers: mock.MagicMock) -> None:
    assert post().status_code == 200
    assert order(helpers) == NAMES


def test_a_failed_embedding_searches_by_keywords_and_says_so(helpers: mock.MagicMock) -> None:
    helpers.embed_question.return_value = (None, ["vector"])
    helpers.hybrid_search.return_value = (["hit"], False)

    post()

    assert helpers.hybrid_search.call_args.args[1] is None
    assert helpers.search_response.call_args.args[5] == ["vector"]
    assert helpers.judge_weak_match.call_args.args[2] is False


def test_a_failed_vector_leg_is_reported_as_degraded(helpers: mock.MagicMock) -> None:
    helpers.hybrid_search.return_value = (["hit"], False)
    post()
    assert helpers.search_response.call_args.args[5] == ["vector"]
    assert helpers.judge_weak_match.call_args.args[2] is False


def test_a_failed_reranker_is_reported_as_degraded(helpers: mock.MagicMock) -> None:
    helpers.rerank_hits.return_value = (["hit"], False)
    post()
    assert helpers.search_response.call_args.args[5] == ["rerank"]


def test_search_down_is_503(helpers: mock.MagicMock) -> None:
    helpers.hybrid_search.side_effect = SearchUnavailable()
    response = post()
    assert response.status_code == 503
    assert response.data["error"]["code"] == "search_unavailable"
    helpers.keep_hits_in_scope.assert_not_called()


def test_an_empty_collaborative_never_reaches_elasticsearch(helpers: mock.MagicMock) -> None:
    helpers.scope_has_no_datasets.return_value = True
    assert post().status_code == 200
    helpers.embed_question.assert_not_called()
    helpers.hybrid_search.assert_not_called()


def test_an_over_long_question_is_400(helpers: mock.MagicMock) -> None:
    assert post({"scope": "platform", "query": "x" * 501}).status_code == 400
    helpers.resolve_scope.assert_not_called()
