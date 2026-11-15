"""Layer 3: the query endpoint's order of checks, helpers mocked (QV1).

Nothing may reach the data database until scope, corpus, profile, analysability
and the spec have all passed.
"""

from typing import Any, Iterator
from unittest import mock

import pytest
from rest_framework.test import APIRequestFactory

from api.services.query_engine.errors import (
    DataRefreshing,
    NotAnalysable,
    NotFound,
    ProfileNotReady,
    QueryTooSlow,
)
from api.services.query_engine.query_spec import SpecError
from api.views.query_engine.query_view import ResourceQueryView

VIEW = "api.views.query_engine.query_view"
RESOURCE_ID = "8c1d2a3e-0000-4000-8000-000000000001"


@pytest.fixture
def helpers() -> Iterator[mock.MagicMock]:
    calls = mock.MagicMock()
    calls.query_response.return_value = {"rows": []}
    names = [
        "resolve_scope",
        "get_resource_in_scope",
        "require_ready_profile",
        "require_analysable",
        "validate_query_spec",
        "compile_query",
        "run_read_only_query",
        "query_response",
    ]
    with mock.patch.multiple(VIEW, **{name: getattr(calls, name) for name in names}), mock.patch(
        "api.views.query_engine.base.InternalQeView.authentication_classes", []
    ), mock.patch("api.views.query_engine.base.InternalQeView.permission_classes", []):
        yield calls


def post(body: Any = None) -> Any:
    request = APIRequestFactory().post(
        f"/api/internal/qe/resources/{RESOURCE_ID}/query/",
        body or {"scope": "platform", "measures": [{"fn": "count"}]},
        format="json",
    )
    return ResourceQueryView.as_view()(request, resource_id=RESOURCE_ID)


def called(calls: mock.MagicMock) -> list:
    return [name for name, _, _ in calls.mock_calls if "." not in name]


def test_runs_the_checks_then_the_query_in_order(helpers: mock.MagicMock) -> None:
    assert post().status_code == 200
    assert called(helpers) == [
        "resolve_scope",
        "get_resource_in_scope",
        "require_ready_profile",
        "require_analysable",
        "validate_query_spec",
        "compile_query",
        "run_read_only_query",
        "query_response",
    ]


@pytest.mark.parametrize(
    "failing,error,status",
    [
        ("get_resource_in_scope", NotFound(), 404),
        ("require_ready_profile", ProfileNotReady(), 409),
        ("require_analysable", NotAnalysable(details={"reasons": ["no_numeric_measure"]}), 422),
        ("validate_query_spec", SpecError("measures needs at least one entry."), 400),
    ],
)
def test_a_failed_check_never_compiles_or_runs_anything(
    helpers: mock.MagicMock, failing: str, error: Exception, status: int
) -> None:
    getattr(helpers, failing).side_effect = error

    response = post()

    assert response.status_code == status
    helpers.compile_query.assert_not_called()
    helpers.run_read_only_query.assert_not_called()


@pytest.mark.parametrize(
    "error,status,code",
    [(QueryTooSlow(), 422, "query_too_slow"), (DataRefreshing(), 409, "data_refreshing")],
)
def test_database_outcomes_map_to_their_status(
    helpers: mock.MagicMock, error: Exception, status: int, code: str
) -> None:
    helpers.run_read_only_query.side_effect = error

    response = post()

    assert response.status_code == status
    assert response.data["error"]["code"] == code


def test_a_body_without_scope_is_400_before_anything_runs(helpers: mock.MagicMock) -> None:
    response = post({"measures": [{"fn": "count"}]})
    assert response.status_code == 400
    helpers.resolve_scope.assert_not_called()
