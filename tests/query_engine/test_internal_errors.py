"""Layer 4: internal endpoints never leak error text (catch-all 500, input errors)."""

import logging
from typing import Any, Callable
from unittest import mock

import pytest

MARKER = "cell-value-Kamrup-12345"


@pytest.mark.django_db
def test_an_unexpected_error_is_a_fixed_500_without_its_text(api: Callable, caplog: Any) -> None:
    caplog.set_level(logging.DEBUG)
    with mock.patch(
        "api.views.query_engine.scope_view.resolve_scope", side_effect=RuntimeError(MARKER)
    ):
        response = api().get("/api/internal/qe/scope/", {"scope": "platform"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Something went wrong."}
    }
    assert MARKER not in response.content.decode()
    assert MARKER not in caplog.text
    assert "qe_request_failed" in caplog.text


@pytest.mark.django_db
def test_an_invalid_field_names_the_field_and_code_but_not_the_value(api: Callable) -> None:
    sent = "collaborative:" + "x" * 80
    response = api().get("/api/internal/qe/scope/", {"scope": sent})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "bad_request"
    assert error["fields"] == {"scope": ["max_length"]}
    assert sent not in response.content.decode()
