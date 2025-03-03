from typing import Any, Dict

import structlog
from django.db import connection
from django.http import HttpRequest, JsonResponse
from elasticsearch import Elasticsearch
from redis import Redis
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

logger = structlog.get_logger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request: HttpRequest) -> JsonResponse:
    """
    Check the health of all required services.
    Returns a JSON response with the status of each service.
    """
    status: Dict[str, Dict[str, Any]] = {
        "database": {"status": "unknown"},
        "elasticsearch": {"status": "unknown"},
        "redis": {"status": "unknown"},
    }

    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            status["database"] = {
                "status": "healthy",
                "message": "Successfully connected to database",
            }
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        status["database"] = {
            "status": "unhealthy",
            "message": f"Failed to connect to database: {str(e)}",
        }

    # Check Elasticsearch
    try:
        es = Elasticsearch()
        if es.ping():
            status["elasticsearch"] = {
                "status": "healthy",
                "message": "Successfully connected to Elasticsearch",
            }
        else:
            raise Exception("Elasticsearch ping failed")
    except Exception as e:
        logger.error("Elasticsearch health check failed", error=str(e))
        status["elasticsearch"] = {
            "status": "unhealthy",
            "message": f"Failed to connect to Elasticsearch: {str(e)}",
        }

    # Check Redis
    try:
        redis = Redis()
        redis.ping()
        status["redis"] = {
            "status": "healthy",
            "message": "Successfully connected to Redis",
        }
    except Exception as e:
        logger.error("Redis health check failed", error=str(e))
        status["redis"] = {
            "status": "unhealthy",
            "message": f"Failed to connect to Redis: {str(e)}",
        }

    # Overall status
    overall_status = all(service["status"] == "healthy" for service in status.values())

    response = {
        "status": "healthy" if overall_status else "unhealthy",
        "services": status,
    }

    return JsonResponse(response)
