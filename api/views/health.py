import os
from typing import Any, Dict

import requests
import structlog
from django.conf import settings
from django.core.cache import cache
from django.db import connection, connections
from django.http import HttpRequest, JsonResponse
from elasticsearch import Elasticsearch
from opentelemetry import trace
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api.utils.telemetry_utils import trace_method, track_metrics

logger = structlog.get_logger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
@trace_method(name="health_check", attributes={"component": "health"})
@track_metrics(name="health_check")
def health_check(request: HttpRequest) -> JsonResponse:
    """Check the health of all required services."""
    current_span = trace.get_current_span()

    status: Dict[str, Dict[str, Any]] = {
        "database": {"status": "unknown"},
        "elasticsearch": {"status": "unknown"},
        "redis": {"status": "unknown"},
        "telemetry": {"status": "unknown"},
    }

    # Check database.
    #
    # Two distinct checks, because they fail independently:
    #
    #   1. The request's own connection still works.
    #   2. A NEW connection can still be opened.
    #
    # Only checking (1) is how this endpoint reported
    # {"database": "healthy"} in 0.44s while Postgres was refusing new
    # connections with "FATAL: sorry, too many clients already" and both the
    # login endpoint and the deploy pipeline were failing on exactly that. The
    # existing connection is already established, so it keeps answering
    # SELECT 1 no matter how saturated the server is - which made a green
    # health check actively misleading during an outage.
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        # Deliberately a fresh connection, closed immediately. This is the
        # check that catches connection exhaustion.
        new_connection = connections.create_connection("default")
        try:
            new_connection.ensure_connection()
        finally:
            new_connection.close()

        status["database"] = {
            "status": "healthy",
            "message": "Successfully connected to database",
        }
        if current_span:
            current_span.set_attribute("database.status", "healthy")
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        status["database"] = {
            "status": "unhealthy",
            "message": f"Failed to connect to database: {str(e)}",
        }
        if current_span:
            current_span.set_attribute("database.status", "unhealthy")
            current_span.set_attribute("database.error", str(e))

    # Check Elasticsearch using Django settings
    try:
        es_settings = settings.ELASTICSEARCH_DSL["default"]
        es = Elasticsearch(
            hosts=es_settings["hosts"], http_auth=es_settings["http_auth"]
        )
        if es.ping():
            status["elasticsearch"] = {
                "status": "healthy",
                "message": "Successfully connected to Elasticsearch",
            }
            if current_span:
                current_span.set_attribute("elasticsearch.status", "healthy")
        else:
            raise Exception("Elasticsearch ping failed")
    except Exception as e:
        logger.error("Elasticsearch health check failed", error=str(e))
        status["elasticsearch"] = {
            "status": "unhealthy",
            "message": f"Failed to connect to Elasticsearch: {str(e)}",
        }
        if current_span:
            current_span.set_attribute("elasticsearch.status", "unhealthy")
            current_span.set_attribute("elasticsearch.error", str(e))

    # Check Redis using Django's cache settings
    try:
        cache.set("health_check", "ok", timeout=1)
        result = cache.get("health_check")
        if result != "ok":
            raise Exception("Cache get/set test failed")

        status["redis"] = {
            "status": "healthy",
            "message": "Successfully connected to Redis",
        }
        if current_span:
            current_span.set_attribute("redis.status", "healthy")
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        status["redis"] = {
            "status": "unhealthy",
            "message": f"Failed to connect to Redis: {str(e)}",
        }
        if current_span:
            current_span.set_attribute("redis.status", "unhealthy")
            current_span.set_attribute("redis.error", str(e))

    # Check OpenTelemetry collector, but only when telemetry is actually
    # configured. DataSpace/settings.py gives TELEMETRY_URL a hardcoded
    # otel-collector default even when the env var is unset, so without this
    # guard a deployment that deliberately runs no collector (as this one
    # does) probes a host that cannot resolve and logs an ERROR on every
    # single health check -- roughly every 30s, forever, for something
    # optional.
    if not os.environ.get("TELEMETRY_URL"):
        status["telemetry"] = {
            "status": "not_configured",
            "message": "TELEMETRY_URL is unset; no OpenTelemetry collector expected",
        }
        if current_span:
            current_span.set_attribute("telemetry.status", "not_configured")
    else:
        try:
            # Extract host and port from TELEMETRY_URL
            telemetry_url = settings.TELEMETRY_URL.replace("http://", "").replace(
                "https://", ""
            )
            host = telemetry_url.split(":")[0]
            # Use default health check port 13133 instead of gRPC port
            health_url = f"http://{host}:13133/health"  # OpenTelemetry collector health check endpoint

            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                status["telemetry"] = {
                    "status": "healthy",
                    "message": "Successfully connected to OpenTelemetry collector",
                }
                if current_span:
                    current_span.set_attribute("telemetry.status", "healthy")
            else:
                raise Exception(
                    f"Health check returned status code {response.status_code}"
                )

        except Exception as e:
            logger.error("Telemetry health check failed", error=str(e))
            status["telemetry"] = {
                "status": "unhealthy",
                "message": f"Failed to connect to OpenTelemetry collector: {str(e)}",
            }
            if current_span:
                current_span.set_attribute("telemetry.status", "unhealthy")
                current_span.set_attribute("telemetry.error", str(e))

    # Overall status: database/elasticsearch/redis are required for the app
    # to actually serve requests. telemetry is observability-only (this
    # deployment topology deliberately runs without otel-collector) and is
    # reported above for visibility, but must not gate 200 vs 503 -- a
    # health check that fails a deploy because optional tracing
    # infrastructure isn't running is a false negative.
    required_services = ("database", "elasticsearch", "redis")
    overall_status = all(status[name]["status"] == "healthy" for name in required_services)

    if current_span:
        current_span.set_attribute(
            "overall.status", "healthy" if overall_status else "unhealthy"
        )

    data = {
        "status": "healthy" if overall_status else "unhealthy",
        "services": status,
        "git_sha": os.environ.get("GIT_COMMIT_SHA", "unknown"),
    }

    return JsonResponse(data, status=200 if overall_status else 503)
