"""Recognising the query engine's own Keycloak service token on internal endpoints.

The query engine calls ``/api/internal/qe/`` with a client-credentials token
from its own confidential Keycloak client. ``QueryEngineServiceAuthentication``
asks Keycloak about the token (introspection) and turns any active token into
a ``ServicePrincipal``; ``IsQueryEngineService`` (authorization/permissions.py)
then lets through only the configured client holding the configured role.

- No Authorization header → not authenticated (401).
- Inactive, expired or unreadable token, or Keycloak unreachable → 401.
- Active but not the engine (an end user, an admin, the right client without
  the role) → 403 from the permission.

The service role must be a realm role or a client role on the backend's own
client (KEYCLOAK_CLIENT_ID): that is all the shared role reader looks at.

Never creates or updates a User row. The default Keycloak authentication
would try (a service account has no email, so it fails). Verdicts are cached
under the token's SHA-256 for at most 60 seconds and never past its expiry;
the raw token is never stored or logged.

Docs: api/views/query_engine/architecture.md
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import structlog
from django.conf import settings
from django.core.cache import cache
from keycloak.exceptions import KeycloakError
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from api.utils.keycloak_utils import keycloak_manager

logger = structlog.get_logger("dataspace.query_engine.auth")

TOKEN_CACHE_PREFIX = "qe_service_token:"
MAX_CACHE_SECONDS = 60


@dataclass(frozen=True)
class ServicePrincipal:
    """Who called with an active Keycloak token: the issuing client and whether it is the engine."""

    client_id: str
    is_query_engine_service: bool

    is_authenticated = True
    is_anonymous = False
    is_superuser = False
    is_staff = False
    pk = None
    id = None


class QueryEngineServiceAuthentication(BaseAuthentication):
    """DRF authentication for the internal query-engine endpoints only."""

    def authenticate(self, request: Request) -> Optional[Tuple[ServicePrincipal, None]]:
        token = _bearer_token(request)
        if token is None:
            return None
        return _principal_for(token), None

    def authenticate_header(self, request: Request) -> str:
        return 'Bearer realm="dataspace-internal"'


def _bearer_token(request: Request) -> Optional[str]:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.lower().startswith("bearer "):
        return None
    return header[7:].strip() or None


def _now() -> float:
    return time.time()


def _principal_for(token: str) -> ServicePrincipal:
    key = TOKEN_CACHE_PREFIX + hashlib.sha256(token.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return ServicePrincipal(**cached)

    info = _introspect(token)
    seconds_left = int(info.get("exp", 0) - _now())
    if not info.get("active") or seconds_left <= 0:
        logger.info("qe_service_token_refused", reason="inactive")
        raise AuthenticationFailed("Invalid or expired token")

    principal = _principal_from(info)
    if not principal.is_query_engine_service:
        logger.warning("qe_service_token_not_service", client_id=principal.client_id)
    cache.set(
        key,
        {
            "client_id": principal.client_id,
            "is_query_engine_service": principal.is_query_engine_service,
        },
        timeout=min(MAX_CACHE_SECONDS, seconds_left),
    )
    return principal


def _introspect(token: str) -> Dict[str, Any]:
    try:
        info = keycloak_manager.keycloak_openid.introspect(token)
    except KeycloakError as error:
        logger.warning(
            "qe_service_token_refused",
            reason="introspection_failed",
            error_type=type(error).__name__,
        )
        raise AuthenticationFailed("Could not check the token") from error
    return info if isinstance(info, dict) else {}


def _principal_from(info: Dict[str, Any]) -> ServicePrincipal:
    client_id = str(info.get("azp") or info.get("client_id") or "")
    expected_client = settings.QE_SERVICE_CLIENT_ID
    roles = keycloak_manager.get_user_roles_from_token_info(info)
    is_service = bool(expected_client) and client_id == expected_client
    return ServicePrincipal(
        client_id=client_id,
        is_query_engine_service=is_service and settings.QE_SERVICE_ROLE in roles,
    )
