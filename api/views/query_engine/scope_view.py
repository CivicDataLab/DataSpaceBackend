"""GET /api/internal/qe/scope/ — what a scope covers right now.

The query engine calls this when a conversation picks a collaborative, and
once per evaluation to learn a scope's dataset ids. Service token only; any
error (bad scope 400, unpublished or unknown collaborative 404) is turned into
the standard error shape by InternalQeView.

Docs: ./architecture.md
"""

from rest_framework.request import Request
from rest_framework.response import Response

from api.services.query_engine.scope import resolve_scope, scope_summary
from api.views.query_engine.base import InternalQeView
from api.views.query_engine.serializers import ScopeRequestSerializer, read_input


class ScopeView(InternalQeView):
    def get(self, request: Request) -> Response:
        # Read the scope and whether the caller wants its dataset ids.
        params = read_input(ScopeRequestSerializer, request.query_params)

        # Work out what the scope covers right now (404 for a collaborative that isn't published).
        scope = resolve_scope(params["scope"])

        # Describe it: kind, title, dataset count and, when asked, the dataset ids.
        return Response(scope_summary(scope, include_dataset_ids=params["include_dataset_ids"]))
