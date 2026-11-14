"""The query-engine data layer's errors, and the one place they become HTTP responses.

Helpers raise these; the internal views turn them into
``{"error": {"code", "message", ...}}`` with ``error_response``. Messages are
fixed text written here: they never echo dataset content, column values, the
search query or anything else the caller sent. ``log_fields`` (ids and a
reason code) go to the log only, so a 404 can hide whether something exists
while the log still says why it was refused.

Docs: api/views/query_engine/architecture.md
"""

from typing import Any, Dict, Optional

from rest_framework.response import Response


class QueryEngineError(Exception):
    """Base class: an HTTP status, a stable code and a safe message."""

    status = 500
    code = "internal_error"
    message = "Something went wrong."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        details: Optional[Dict[str, Any]] = None,
        **log_fields: Any,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        self.log_fields = log_fields
        super().__init__(self.message)


class BadRequest(QueryEngineError):
    status = 400
    code = "bad_request"
    message = "The request is not valid."


class BadScope(BadRequest):
    code = "bad_scope"
    message = "scope must be 'platform' or 'collaborative:<12-character public id>'."


class NotFound(QueryEngineError):
    """Not there, not in the corpus, or not in the scope: the caller can't tell which."""

    status = 404
    code = "not_found"
    message = "Not found in this scope."


class ScopeNotFound(NotFound):
    code = "scope_not_found"
    message = "No published collaborative with that id is available to the query engine."


class ProfileNotReady(QueryEngineError):
    status = 409
    code = "profile_not_ready"
    message = "This table's profile is not ready yet; try again in a few minutes."


class DataRefreshing(QueryEngineError):
    status = 409
    code = "data_refreshing"
    message = "This table is being refreshed; try again shortly."


class FactsChanged(QueryEngineError):
    status = 409
    code = "facts_changed"
    message = "The facts changed since this summary was written; nothing was stored."


class NotAnalysable(QueryEngineError):
    status = 422
    code = "not_analysable"
    message = "This table can't be analysed."


class QueryTooSlow(QueryEngineError):
    status = 422
    code = "query_too_slow"
    message = "The query took too long; narrow it with filters or fewer groups."


class QueryFailed(QueryEngineError):
    status = 422
    code = "query_failed"
    message = "The database could not run this query."


class SummaryRejected(QueryEngineError):
    status = 422
    code = "summary_rejected"
    message = "The summary was not accepted."


class InternalQueryError(QueryEngineError):
    """Something that should be impossible, such as a write reaching the data database."""


class SearchUnavailable(QueryEngineError):
    status = 503
    code = "search_unavailable"
    message = "Search is unavailable right now."


def error_response(error: QueryEngineError) -> Response:
    """The JSON response for an error: its status, code, message and any details."""
    body: Dict[str, Any] = {"code": error.code, "message": error.message, **error.details}
    return Response({"error": body}, status=error.status)
