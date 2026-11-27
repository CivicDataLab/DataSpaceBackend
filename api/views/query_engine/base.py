"""The base class every internal query-engine view uses.

It fixes who may call (the engine's service token only: QueryEngineServiceAuthentication
+ IsQueryEngineService, nothing else), keeps the views out of the public API
docs, and turns every error into the same ``{"error": {"code", "message"}}``
shape, so each view's flow just calls its helpers and lets typed errors rise:

- a query-engine error → its own status and code, logged with ids and a reason code;
- DRF's auth and parsing errors → 401 / 403 / 400 with a fixed message;
- anything unexpected → 500 ``internal_error``, logged by class, Postgres code
  and location only (database messages can quote cell values).

Docs: ./architecture.md
"""

import structlog
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from api.services.query_engine.errors import QueryEngineError, error_response
from api.utils.data_tables import error_fields
from authorization.permissions import IsQueryEngineService
from authorization.service_auth import QueryEngineServiceAuthentication

logger = structlog.get_logger("dataspace.query_engine.views")

_DRF_ERRORS = {
    401: ("not_authenticated", "A valid query-engine service token is required."),
    403: ("forbidden", "This endpoint is only for the query engine."),
    400: ("bad_request", "The request body could not be read."),
}


class InternalQeView(APIView):
    authentication_classes = [QueryEngineServiceAuthentication]
    permission_classes = [IsQueryEngineService]
    swagger_schema = None

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, QueryEngineError):
            log = logger.error if exc.status >= 500 else logger.info
            log(
                "qe_request_refused",
                path=self.request.path,
                status=exc.status,
                code=exc.code,
                **exc.log_fields,
            )
            return error_response(exc)
        if isinstance(exc, exceptions.APIException):
            response = super().handle_exception(exc)
            code, message = _DRF_ERRORS.get(
                response.status_code, (str(exc.default_code), "The request was refused.")
            )
            if response.status_code == 401 and isinstance(exc, exceptions.AuthenticationFailed):
                code = "authentication_failed"
            response.data = {"error": {"code": code, "message": message}}
            return response
        logger.error("qe_request_failed", path=self.request.path, **error_fields(exc))
        return error_response(QueryEngineError())
