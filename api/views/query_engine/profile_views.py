"""GET datasets/<id>/profile/ and GET resources/<id>/profile/ — what a dataset or table holds.

Both re-check, on every call, that the item is in the corpus and inside the
caller's scope (404 otherwise, never saying whether it exists). A table's
profile must be READY for its current data table (409 ``profile_not_ready``
while ``qe_sync`` catches up after an upload). Views are size-capped and
label publisher text as untrusted and summaries as generated.

Docs: ./architecture.md
"""

from uuid import UUID

from rest_framework.request import Request
from rest_framework.response import Response

from api.services.query_engine.corpus import get_dataset_in_scope, get_resource_in_scope
from api.services.query_engine.profile_views import dataset_profile_view, resource_profile_view
from api.services.query_engine.profiles import load_dataset_tables, require_ready_profile
from api.services.query_engine.scope import resolve_scope
from api.views.query_engine.base import InternalQeView
from api.views.query_engine.serializers import (
    ResourceProfileRequestSerializer,
    ScopeOnlySerializer,
    read_input,
)


class DatasetProfileView(InternalQeView):
    def get(self, request: Request, dataset_id: UUID) -> Response:
        # Read the scope.
        params = read_input(ScopeOnlySerializer, request.query_params)

        # Work out what the scope covers right now.
        scope = resolve_scope(params["scope"])

        # The dataset, only if it is in the corpus and in this scope (404 otherwise).
        dataset = get_dataset_in_scope(dataset_id, scope)

        # Its tables with their profiles, and its other resources.
        tables = load_dataset_tables(dataset)

        # Build the size-capped view from those and the dataset's metadata.
        return Response(dataset_profile_view(dataset, tables))


class ResourceProfileView(InternalQeView):
    def get(self, request: Request, resource_id: UUID) -> Response:
        # Read the scope and any columns asked for in detail.
        params = read_input(ResourceProfileRequestSerializer, request.query_params)

        # Work out what the scope covers right now.
        scope = resolve_scope(params["scope"])

        # The table, only if it is analysable, in the corpus and in this scope (404 otherwise).
        resource = get_resource_in_scope(resource_id, scope)

        # Its profile, only when computed from its current data (409 while qe_sync catches up).
        profile = require_ready_profile(resource)

        # The compact view, or the detail of the columns asked for.
        return Response(resource_profile_view(resource, profile, params.get("columns")))
