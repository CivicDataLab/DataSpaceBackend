"""POST resources/<id>/query/ — run one structured analysis on a table, read-only.

The body is a query spec (see api/services/query_engine/query_spec.py) plus
its scope. Nothing reaches the data database until every check passed: the
table is in the corpus and the scope (404), its profile is current (409
``profile_not_ready``), it can be analysed (422 ``not_analysable``), and the
spec is valid for it (400). The statement then runs in a read-only,
time-limited transaction; too slow → 422 ``query_too_slow``; the table was
replaced by a re-upload mid-read → 409 ``data_refreshing``. The answer carries
the exact SQL that ran and where the data came from.

Docs: ./architecture.md
"""

from uuid import UUID

from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response

from api.services.query_engine.corpus import get_resource_in_scope
from api.services.query_engine.data_reader import run_read_only_query
from api.services.query_engine.profiles import require_analysable, require_ready_profile
from api.services.query_engine.query_compiler import compile_query
from api.services.query_engine.query_results import query_response
from api.services.query_engine.query_spec import validate_query_spec
from api.services.query_engine.scope import resolve_scope
from api.views.query_engine.base import InternalQeView
from api.views.query_engine.serializers import QueryRequestSerializer, read_input


class ResourceQueryView(InternalQeView):
    def post(self, request: Request, resource_id: UUID) -> Response:
        # Read the scope; the rest of the body is the query spec.
        body = read_input(QueryRequestSerializer, {"body": request.data})["body"]

        # Work out what the scope covers right now.
        scope = resolve_scope(body["scope"])

        # The table, only if it is analysable, in the corpus and in this scope (404 otherwise).
        resource = get_resource_in_scope(resource_id, scope)

        # Its profile, only when computed from its current data (409 while qe_sync catches up).
        profile = require_ready_profile(resource)

        # Tables with no rows or no numbers can't be analysed (422 with the reasons).
        require_analysable(profile.stats, resource)

        # Check the spec against the profile: known columns, typed values, caps (400 otherwise).
        spec = validate_query_spec(body, profile.stats)

        # Build one parameterised SELECT for it.
        compiled = compile_query(spec, profile.stats, resource.resourcedatatable.table_name)

        # Run it read-only, with a time limit and a row cap.
        result = run_read_only_query(
            compiled.sql,
            compiled.params,
            timeout_ms=settings.QE_QUERY_TIMEOUT_MS,
            max_rows=compiled.max_rows,
        )

        # Answer with the rows, the SQL that ran, and where the data came from.
        return Response(query_response(spec, compiled, result, resource, profile))
