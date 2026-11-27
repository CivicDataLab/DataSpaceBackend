"""Layer 4: who may call the internal query-engine endpoints (auth matrix, AUTH-MW, Swagger).

Every endpoint under /api/internal/qe/ is called through the real URL
configuration with the real service-auth class; only Keycloak's introspection
is mocked. Each endpoint's own test file proves the service token gets a 2xx.
"""

import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest import mock

import pytest
from django.test import Client

from authorization.models import User

SOME_ID = str(uuid.uuid4())

# (method, path, body) for every internal endpoint; later phases add theirs here.
ENDPOINTS: List[Tuple[str, str, Optional[Dict[str, Any]]]] = [
    ("get", "/api/internal/qe/scope/?scope=platform", None),
    ("post", "/api/internal/qe/search/", {"scope": "platform", "query": "rain"}),
    ("get", "/api/internal/qe/summaries/pending/", None),
    ("put", f"/api/internal/qe/summaries/resource/{SOME_ID}/", {"facts_hash": "0" * 64}),
    ("get", f"/api/internal/qe/datasets/{SOME_ID}/profile/?scope=platform", None),
    ("get", f"/api/internal/qe/resources/{SOME_ID}/profile/?scope=platform", None),
    ("post", f"/api/internal/qe/resources/{SOME_ID}/query/", {"scope": "platform"}),
]


def call(client: Any, method: str, path: str, body: Optional[Dict[str, Any]]) -> Any:
    if method == "get":
        return client.get(path)
    return getattr(client, method)(path, body or {}, format="json")


@pytest.mark.django_db
@pytest.mark.parametrize("method,path,body", ENDPOINTS)
class TestAuthMatrix:
    def test_no_token_is_401(self, api: Callable, method: str, path: str, body: Any) -> None:
        response = call(api(None), method, path, body)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"

    def test_an_invalid_token_is_401(
        self, api: Callable, method: str, path: str, body: Any
    ) -> None:
        response = call(api("inactive-token"), method, path, body)
        assert response.status_code == 401

    def test_an_end_user_token_is_403(
        self, api: Callable, method: str, path: str, body: Any
    ) -> None:
        response = call(api("end-user-token"), method, path, body)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"

    def test_an_admin_without_the_service_role_is_403(
        self, api: Callable, method: str, path: str, body: Any
    ) -> None:
        response = call(api("admin-token"), method, path, body)
        assert response.status_code == 403

    def test_no_user_row_is_ever_written(
        self, api: Callable, method: str, path: str, body: Any
    ) -> None:
        for token in ("service-token", "end-user-token", "admin-token"):
            call(api(token), method, path, body)
        assert User.objects.count() == 0


KEYCLOAK_MIDDLEWARE = "authorization.middleware.KeycloakAuthenticationMiddleware"


@pytest.mark.django_db
class TestKeycloakMiddlewareSkipsInternalPaths:
    """The test settings remove the global Keycloak middleware; these switch it back on."""

    @pytest.fixture
    def with_middleware(self, settings: Any) -> None:
        settings.MIDDLEWARE = [*settings.MIDDLEWARE, KEYCLOAK_MIDDLEWARE]

    def test_a_service_call_introspects_once_and_writes_no_user(
        self, with_middleware: None, keycloak_introspect: mock.MagicMock
    ) -> None:
        with mock.patch("authorization.middleware.keycloak_auth.logger") as middleware_log:
            response = Client().get(
                "/api/internal/qe/scope/?scope=platform",
                HTTP_AUTHORIZATION="Bearer service-token",
            )

        assert response.status_code == 200
        assert keycloak_introspect.call_count == 1
        assert User.objects.count() == 0
        middleware_log.error.assert_not_called()

    def test_a_public_path_still_goes_through_the_middleware(self, with_middleware: None) -> None:
        with mock.patch(
            "authorization.middleware.keycloak_auth.get_user_from_keycloak_token"
        ) as get_user:
            from django.contrib.auth.models import AnonymousUser

            get_user.return_value = AnonymousUser()
            Client().get("/api/search/dataset/", HTTP_AUTHORIZATION="Bearer end-user-token")
        get_user.assert_called_once()


def test_internal_views_are_left_out_of_the_api_docs() -> None:
    from drf_yasg import openapi
    from drf_yasg.generators import OpenAPISchemaGenerator

    generator = OpenAPISchemaGenerator(openapi.Info(title="DataSpace", default_version="v1"))
    endpoints = generator.get_endpoints(request=None)
    internal = [path for path in endpoints if path.startswith("/api/internal/")]
    assert internal == []
    # Guard: the generator really does see the rest of the API.
    assert any(path.startswith("/api/") for path in endpoints)
