from typing import Any, Dict, Optional, Type, Union

from django.contrib.auth import get_user_model
from django.db.models import Model
from django.http import HttpRequest

# Import all activity trackers
from api.activities.dataset import (
    track_dataset_created,
    track_dataset_deleted,
    track_dataset_published,
    track_dataset_updated,
)
from api.activities.organization import (
    track_member_added,
    track_member_removed,
    track_member_role_changed,
    track_organization_created,
    track_organization_updated,
)
from api.activities.resource import (
    track_resource_created,
    track_resource_deleted,
    track_resource_downloaded,
    track_resource_previewed,
    track_resource_updated,
)
from api.activities.usecase import (
    track_dataset_added_to_usecase,
    track_dataset_removed_from_usecase,
    track_usecase_created,
    track_usecase_deleted,
    track_usecase_published,
    track_usecase_updated,
)

User = get_user_model()


# Re-export all activity tracking functions for easier imports
__all__ = [
    # Dataset activities
    "track_dataset_created",
    "track_dataset_updated",
    "track_dataset_published",
    "track_dataset_deleted",
    # Organization activities
    "track_organization_created",
    "track_organization_updated",
    "track_member_added",
    "track_member_removed",
    "track_member_role_changed",
    # Resource activities
    "track_resource_created",
    "track_resource_updated",
    "track_resource_deleted",
    "track_resource_downloaded",
    "track_resource_previewed",
    # UseCase activities
    "track_usecase_created",
    "track_usecase_updated",
    "track_usecase_published",
    "track_usecase_deleted",
    "track_dataset_added_to_usecase",
    "track_dataset_removed_from_usecase",
]
