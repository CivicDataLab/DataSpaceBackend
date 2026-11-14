"""Layer 2: the query engine's service-token check (AUTH1)."""

from typing import Any, Dict, Optional
from unittest import mock

import pytest
from keycloak.exceptions import KeycloakError
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from authorization.models import User
from authorization.permissions import IsQueryEngineService
from authorization.service_auth import QueryEngineServiceAuthentication, ServicePrincipal
from tests.query_engine.conftest import introspection, without_role

INTROSPECT = "api.utils.keycloak_utils.keycloak_manager.keycloak_openid.introspect"


def authenticate(token: Optional[str]) -> Any:
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    request = APIRequestFactory().get("/api/internal/qe/scope/", **headers)
    return QueryEngineServiceAuthentication().authenticate(request)


def allowed(principal: Any) -> bool:
    request = mock.Mock(user=principal)
    return IsQueryEngineService().has_permission(request, view=None)


def answer(info: Dict[str, Any]) -> Any:
    return mock.patch(INTROSPECT, return_value=info)


@pytest.mark.django_db
class TestQueryEngineServiceAuthentication:
    def test_a_service_token_becomes_the_service_principal(self) -> None:
        with answer(introspection("service")):
            principal, _ = authenticate("service-token")

        assert isinstance(principal, ServicePrincipal)
        assert principal.client_id == "dataspace-query-engine-service"
        assert principal.is_authenticated
        assert allowed(principal)

    def test_no_header_leaves_the_request_unauthenticated(self) -> None:
        with mock.patch(INTROSPECT) as introspect:
            assert authenticate(None) is None
        introspect.assert_not_called()

    def test_an_inactive_token_is_refused(self) -> None:
        with answer({"active": False}):
            with pytest.raises(AuthenticationFailed):
                authenticate("old-token")

    def test_a_token_past_its_expiry_is_refused(self) -> None:
        with answer(introspection("service", expires_in=-5)):
            with pytest.raises(AuthenticationFailed):
                authenticate("expired-token")

    def test_an_introspection_error_is_refused(self) -> None:
        with mock.patch(INTROSPECT, side_effect=KeycloakError("down")):
            with pytest.raises(AuthenticationFailed):
                authenticate("service-token")

    def test_an_end_user_token_is_authenticated_but_not_allowed(self) -> None:
        with answer(introspection("end_user")):
            principal, _ = authenticate("end-user-token")
        assert principal.is_authenticated
        assert not allowed(principal)

    def test_the_right_client_without_the_role_is_not_allowed(self) -> None:
        with answer(without_role(introspection("service"))):
            principal, _ = authenticate("service-token")
        assert not allowed(principal)

    def test_the_role_on_another_client_is_not_allowed(self) -> None:
        info = introspection("end_user")
        info["realm_access"]["roles"].append("query-engine-service")
        with answer(info):
            principal, _ = authenticate("end-user-token")
        assert not allowed(principal)

    def test_a_client_role_on_the_backend_client_counts(self, settings: Any) -> None:
        info = without_role(introspection("service"))
        info["resource_access"][settings.KEYCLOAK_CLIENT_ID] = {"roles": ["query-engine-service"]}
        with answer(info):
            principal, _ = authenticate("service-token")
        assert allowed(principal)

    def test_a_role_on_the_engines_own_client_does_not_count(self) -> None:
        info = without_role(introspection("service"))
        info["resource_access"]["dataspace-query-engine-service"] = {
            "roles": ["query-engine-service"]
        }
        with answer(info):
            principal, _ = authenticate("service-token")
        assert not allowed(principal)

    def test_nothing_is_allowed_when_no_service_client_is_configured(self, settings: Any) -> None:
        settings.QE_SERVICE_CLIENT_ID = ""
        with answer(introspection("service", azp="", client_id="")):
            principal, _ = authenticate("service-token")
        assert not allowed(principal)

    def test_a_django_user_is_never_allowed(self) -> None:
        user = User(username="admin", is_superuser=True)
        assert not allowed(user)

    def test_a_cached_verdict_skips_the_second_introspection(self) -> None:
        with answer(introspection("service")) as introspect:
            authenticate("service-token")
            principal, _ = authenticate("service-token")
        assert introspect.call_count == 1
        assert allowed(principal)

    def test_the_cached_verdict_never_outlives_the_token(self) -> None:
        with answer(introspection("service", expires_in=20)):
            with mock.patch("authorization.service_auth.cache") as cache:
                cache.get.return_value = None
                authenticate("service-token")
        timeout = cache.set.call_args.kwargs["timeout"]
        assert 0 < timeout <= 20

    def test_the_cache_is_never_given_the_raw_token(self) -> None:
        with answer(introspection("service")):
            with mock.patch("authorization.service_auth.cache") as cache:
                cache.get.return_value = None
                authenticate("service-token")
        key = cache.set.call_args.args[0]
        assert "service-token" not in key

    def test_never_creates_or_updates_a_user(self) -> None:
        with answer(introspection("service")):
            authenticate("service-token")
        with answer(introspection("end_user")):
            authenticate("end-user-token")
        assert User.objects.count() == 0
