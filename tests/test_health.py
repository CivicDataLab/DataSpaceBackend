"""Tests for the /health/ endpoint's status-code and git_sha behavior."""

import os
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from django.test import Client, override_settings


class TestHealthCheck(unittest.TestCase):
    """The endpoint must reflect actual dependency health in its status code."""

    def setUp(self) -> None:
        self.client = Client()

    def _mock_healthy_dependencies(self, stack: ExitStack) -> None:
        """Patch ES/Redis/telemetry so the happy path doesn't need real services."""
        # tests/test_settings.py's ELASTICSEARCH_DSL omits http_auth (the real
        # DataSpace/settings.py value always sets it) — health_check reads it
        # unconditionally, so supply it here rather than touching test settings.
        stack.enter_context(
            override_settings(
                ELASTICSEARCH_DSL={
                    "default": {"hosts": "localhost:9200", "http_auth": ("user", "pass")}
                }
            )
        )
        mock_es_instance = MagicMock()
        mock_es_instance.ping.return_value = True
        stack.enter_context(
            patch("api.views.health.Elasticsearch", return_value=mock_es_instance)
        )
        # `cache` is Django's lazy DefaultConnectionProxy — patching .set/.get
        # as attributes on it gets forwarded to the real backend instead of
        # being intercepted, so replace the name binding in the health module
        # wholesale instead.
        cache_store: dict = {}
        mock_cache = MagicMock()
        mock_cache.set.side_effect = lambda k, v, timeout=None: cache_store.__setitem__(k, v)
        mock_cache.get.side_effect = lambda k: cache_store.get(k)
        stack.enter_context(patch("api.views.health.cache", mock_cache))
        mock_get = stack.enter_context(patch("api.views.health.requests.get"))
        mock_get.return_value.status_code = 200

    def test_returns_200_when_all_dependencies_healthy(self) -> None:
        with ExitStack() as stack:
            self._mock_healthy_dependencies(stack)
            response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_returns_503_when_elasticsearch_unhealthy(self) -> None:
        with ExitStack() as stack:
            self._mock_healthy_dependencies(stack)
            mock_es_instance = MagicMock()
            mock_es_instance.ping.return_value = False
            stack.enter_context(
                patch("api.views.health.Elasticsearch", return_value=mock_es_instance)
            )
            response = self.client.get("/health/")

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "unhealthy")
        self.assertEqual(body["services"]["elasticsearch"]["status"], "unhealthy")

    def test_returns_503_when_redis_unhealthy(self) -> None:
        with ExitStack() as stack:
            self._mock_healthy_dependencies(stack)
            mock_cache = MagicMock()
            mock_cache.set.side_effect = Exception("down")
            stack.enter_context(patch("api.views.health.cache", mock_cache))
            response = self.client.get("/health/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["services"]["redis"]["status"], "unhealthy")

    def test_git_sha_defaults_to_unknown(self) -> None:
        with ExitStack() as stack:
            self._mock_healthy_dependencies(stack)
            stack.enter_context(patch.dict(os.environ, {}, clear=False))
            os.environ.pop("GIT_COMMIT_SHA", None)
            response = self.client.get("/health/")

        self.assertEqual(response.json()["git_sha"], "unknown")

    def test_git_sha_reflects_env_var(self) -> None:
        with ExitStack() as stack:
            self._mock_healthy_dependencies(stack)
            stack.enter_context(patch.dict(os.environ, {"GIT_COMMIT_SHA": "abc1234"}))
            response = self.client.get("/health/")

        self.assertEqual(response.json()["git_sha"], "abc1234")


if __name__ == "__main__":
    unittest.main()
