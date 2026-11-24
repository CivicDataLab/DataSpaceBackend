"""Search with a bad `page` or `size` answers 400, not 500 (#303).

Root cause: the REST search views read `page`/`size` with a bare `int()` and sliced the
Elasticsearch query with them. `size=abc` raised in `int()`, `page=0` or `-1` made a
negative slice, and a page past the first 10 000 hits made Elasticsearch refuse the
query; each answered 500, and the type searches returned the raw error text.

Fix: `parse_pagination` in `api/utils/search_pagination.py` checks both before the
search runs (whole numbers of 1 or more, page x size within Elasticsearch's 10 000 result
window) and the views answer 400 with its fixed message. Other failures in the type
searches are logged and answered with a generic message. No test here reaches
Elasticsearch: a search that would run is replaced.
"""

from unittest import mock

import pytest
from elasticsearch_dsl import Search
from rest_framework.test import APIRequestFactory

from api.utils.search_pagination import (
    MAX_RESULT_WINDOW,
    NOT_A_NUMBER_MESSAGE,
    TOO_DEEP_MESSAGE,
    PaginationError,
    parse_pagination,
)
from api.views.search_aimodel import SearchAIModel
from api.views.search_collaborative import SearchCollaborative
from api.views.search_dataset import SearchDataset
from api.views.search_event import SearchEvent
from api.views.search_publication import SearchPublication
from api.views.search_publisher import SearchPublisher
from api.views.search_unified import UnifiedSearch
from api.views.search_usecase import SearchUseCase

VIEWS = {
    "dataset": SearchDataset,
    "usecase": SearchUseCase,
    "collaborative": SearchCollaborative,
    "aimodel": SearchAIModel,
    "publication": SearchPublication,
    "event": SearchEvent,
    "publisher": SearchPublisher,
    "unified": UnifiedSearch,
}

BAD = [
    ({"page": "0"}, NOT_A_NUMBER_MESSAGE),
    ({"page": "-1"}, NOT_A_NUMBER_MESSAGE),
    ({"page": "abc"}, NOT_A_NUMBER_MESSAGE),
    ({"page": "1.5"}, NOT_A_NUMBER_MESSAGE),
    ({"size": "abc"}, NOT_A_NUMBER_MESSAGE),
    ({"size": "0"}, NOT_A_NUMBER_MESSAGE),
    ({"page": "9999"}, TOO_DEEP_MESSAGE),
    ({"size": "10001"}, TOO_DEEP_MESSAGE),
]


# ─── The check ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("params,message", BAD)
def test_bad_values_are_refused(params, message):
    with pytest.raises(PaginationError, match=message.split(".")[0]):
        parse_pagination(params)


@pytest.mark.parametrize(
    "params,expected",
    [
        ({}, (1, 10)),
        ({"page": "", "size": ""}, (1, 10)),
        ({"page": " 2 ", "size": "9"}, (2, 9)),
        ({"page": "1", "size": "120"}, (1, 120)),  # unified "all types" page
        ({"page": "1000", "size": "10"}, (1000, 10)),  # exactly the last allowed hit
        ({"page": "1", "size": str(MAX_RESULT_WINDOW)}, (1, MAX_RESULT_WINDOW)),
    ],
)
def test_good_values_are_returned(params, expected):
    assert parse_pagination(params) == expected


def test_one_past_the_result_window_is_refused():
    with pytest.raises(PaginationError):
        parse_pagination({"page": "1001", "size": "10"})


# ─── The views ────────────────────────────────────────────────────────────────


def get(view, **params):
    request = APIRequestFactory().get("/api/search/x/", params)
    return VIEWS[view].as_view()(request)


@pytest.fixture
def no_search():
    """Fail the test if a refused request still reaches Elasticsearch."""
    with mock.patch.object(Search, "execute", side_effect=AssertionError("search ran")):
        yield


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("params,message", BAD)
def test_views_answer_400_with_a_fixed_message(no_search, view, params, message):
    response = get(view, **params)

    assert response.status_code == 400
    assert response.data == {"error": message}


@pytest.mark.parametrize(
    "view", ["dataset", "usecase", "collaborative", "aimodel", "publication", "event"]
)
def test_search_failure_text_is_not_returned(view):
    failure = RuntimeError("Result window is too large, internal detail")
    with mock.patch.object(Search, "execute", side_effect=failure) as execute:
        response = get(view, page="1")

    assert execute.called  # the failure came from the search, not from earlier
    assert response.status_code == 500
    assert response.data == {"error": "An internal error has occurred."}
