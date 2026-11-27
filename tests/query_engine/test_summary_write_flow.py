"""Layer 3: the summary write endpoint's order of checks, helpers mocked (SV1).

Nothing may be stored unless every check passed; numbers are never checked
on a stale version; every refusal after the version check is counted.
"""

from typing import Any, Iterator
from unittest import mock

import pytest
from rest_framework.test import APIRequestFactory

from api.services.query_engine.errors import FactsChanged, NotFound
from api.views.query_engine.summary_views import SummaryWriteView

VIEW = "api.views.query_engine.summary_views"
ITEM = "8c1d2a3e-0000-4000-8000-000000000001"
NAMES = [
    "get_summary_target",
    "current_facts",
    "require_same_facts",
    "check_summary_text",
    "find_untraced_numbers",
    "record_rejection",
    "save_summary_if_current",
]


@pytest.fixture
def helpers() -> Iterator[mock.MagicMock]:
    calls = mock.MagicMock()
    calls.check_summary_text.return_value = []
    calls.find_untraced_numbers.return_value = []
    calls.save_summary_if_current.return_value = True
    with mock.patch.multiple(VIEW, **{name: getattr(calls, name) for name in NAMES}), mock.patch(
        "api.views.query_engine.base.InternalQeView.authentication_classes", []
    ), mock.patch("api.views.query_engine.base.InternalQeView.permission_classes", []):
        yield calls


def put() -> Any:
    request = APIRequestFactory().put(
        f"/api/internal/qe/summaries/resource/{ITEM}/",
        {"facts_hash": "f" * 64, "text": "x" * 100, "model": "m", "prompt_version": "p"},
        format="json",
    )
    return SummaryWriteView.as_view()(request, level="resource", item_id=ITEM)


def order(calls: mock.MagicMock) -> list:
    return [name for name, _, _ in calls.mock_calls if "." not in name]


def test_checks_run_in_order_and_only_then_it_is_stored(helpers: mock.MagicMock) -> None:
    assert put().status_code == 204
    assert order(helpers) == [
        "get_summary_target",
        "current_facts",
        "require_same_facts",
        "check_summary_text",
        "find_untraced_numbers",
        "save_summary_if_current",
    ]


@pytest.mark.parametrize(
    "failing,error,status",
    [
        ("get_summary_target", NotFound(), 404),
        ("require_same_facts", FactsChanged(), 409),
    ],
)
def test_an_ineligible_or_stale_write_checks_nothing_further_and_counts_nothing(
    helpers: mock.MagicMock, failing: str, error: Exception, status: int
) -> None:
    getattr(helpers, failing).side_effect = error
    assert put().status_code == status
    helpers.find_untraced_numbers.assert_not_called()
    helpers.record_rejection.assert_not_called()
    helpers.save_summary_if_current.assert_not_called()


def test_a_text_rule_refusal_is_counted_and_never_stored(helpers: mock.MagicMock) -> None:
    helpers.check_summary_text.return_value = ["url"]
    assert put().status_code == 422
    helpers.record_rejection.assert_called_once()
    helpers.find_untraced_numbers.assert_not_called()
    helpers.save_summary_if_current.assert_not_called()


def test_an_untraced_number_is_counted_and_never_stored(helpers: mock.MagicMock) -> None:
    helpers.find_untraced_numbers.return_value = ["36"]
    assert put().status_code == 422
    helpers.record_rejection.assert_called_once()
    helpers.save_summary_if_current.assert_not_called()


def test_facts_moving_during_the_write_is_409(helpers: mock.MagicMock) -> None:
    helpers.save_summary_if_current.return_value = False
    assert put().status_code == 409
