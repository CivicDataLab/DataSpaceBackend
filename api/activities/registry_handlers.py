"""Register all activity tracking handlers."""

# mypy: disable-error-code=arg-type
# mypy: disable-error-code=union-attr

from typing import Any, Dict, Optional

from django.http import HttpRequest

# Import all specialized tracking functions
from api.activities.dataset import (
    track_dataset_created,
    track_dataset_published,
    track_dataset_updated,
)
from api.activities.organization import (
    track_organization_created,
    track_organization_updated,
)
from api.activities.registry import register_model_handler
from api.activities.resource import (
    track_resource_created,
    track_resource_downloaded,
    track_resource_previewed,
    track_resource_updated,
)
from api.activities.usecase import (
    track_usecase_created,
    track_usecase_published,
    track_usecase_updated,
)
from authorization.models import User

# Register Dataset handlers
# Register Dataset handlers
register_model_handler(
    "Dataset",
    "created",
    lambda user, instance, data, request: track_dataset_created(
        user, instance, request
    ),
)

register_model_handler(
    "Dataset",
    "updated",
    lambda user, instance, data, request: track_dataset_updated(
        user, instance, data, request
    ),
)

register_model_handler(
    "Dataset",
    "published",
    lambda user, instance, data, request: track_dataset_published(
        user, instance, request
    ),
)

register_model_handler(
    "Dataset",
    "unpublished",
    lambda user, instance, data, request: track_dataset_updated(
        user, instance, {"status": "DRAFT", "action": "unpublished"}, request
    ),
)

# Register Organization handlers
register_model_handler(
    "Organization",
    "created",
    lambda user, instance, data, request: track_organization_created(
        user, instance, request
    ),
)

register_model_handler(
    "Organization",
    "updated",
    lambda user, instance, data, request: track_organization_updated(
        user, instance, data, request
    ),
)

register_model_handler(
    "Organization",
    "deleted",
    lambda user, instance, data, request: track_organization_updated(
        user,
        instance,
        {"action": "deleted", "organization_id": data.get("organization_id")},
        request,
    ),
)

# Register Resource handlers
register_model_handler(
    "Resource",
    "created",
    lambda user, instance, data, request: track_resource_created(
        user, instance, request
    ),
)

register_model_handler(
    "Resource",
    "updated",
    lambda user, instance, data, request: track_resource_updated(
        user, instance, data, request
    ),
)

register_model_handler(
    "Resource",
    "downloaded",
    lambda user, instance, data, request: track_resource_downloaded(
        user, instance, request
    ),
)

register_model_handler(
    "Resource",
    "previewed",
    lambda user, instance, data, request: track_resource_previewed(
        user, instance, request
    ),
)

register_model_handler(
    "Resource",
    "versioned",
    lambda user, instance, data, request: track_resource_updated(
        user,
        instance,
        {
            "action": "versioned",
            "version": data.get("version"),
            "description": data.get("description"),
        },
        request,
    ),
)

register_model_handler(
    "Resource",
    "deleted",
    lambda user, instance, data, request: track_resource_updated(
        user,
        instance,
        {"action": "deleted", "resource_id": data.get("resource_id")},
        request,
    ),
)

# Register UseCase handlers
register_model_handler(
    "UseCase",
    "created",
    lambda user, instance, data, request: track_usecase_created(
        user, instance, request
    ),
)

register_model_handler(
    "UseCase",
    "updated",
    lambda user, instance, data, request: track_usecase_updated(
        user, instance, data, request
    ),
)

register_model_handler(
    "UseCase",
    "published",
    lambda user, instance, data, request: track_usecase_published(
        user, instance, request
    ),
)

register_model_handler(
    "UseCase",
    "unpublished",
    lambda user, instance, data, request: track_usecase_updated(
        user, instance, {"status": "DRAFT", "action": "unpublished"}, request
    ),
)

register_model_handler(
    "UseCase",
    "deleted",
    lambda user, instance, data, request: track_usecase_updated(
        user,
        instance,
        {"action": "deleted", "usecase_id": data.get("usecase_id")},
        request,
    ),
)
