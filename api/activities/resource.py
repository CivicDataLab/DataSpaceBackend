from typing import Any, Dict, Optional

from django.http import HttpRequest

from api.activities.base import track_model_activity
from api.models.Resource import Resource
from authorization.models import User


def track_resource_created(
    user: User, resource: Resource, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when a resource is created.
    """
    track_model_activity(
        actor=user,
        verb="created",
        model_instance=resource,
        target=resource.dataset,  # The dataset is the target
        request=request,
        extra_data={
            "resource_name": resource.name,
            "resource_id": str(resource.id),
            "resource_type": resource.type,
            "dataset_id": str(resource.dataset.id),
            "dataset_title": resource.dataset.title,
        },
    )


def track_resource_updated(
    user: User,
    resource: Resource,
    updated_fields: Optional[Dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a resource is updated.

    Args:
        user: The user performing the update
        resource: The resource being updated
        updated_fields: Dictionary of fields that were updated
        request: The current HTTP request
    """
    track_model_activity(
        actor=user,
        verb="updated",
        model_instance=resource,
        target=resource.dataset,  # The dataset is the target
        request=request,
        extra_data={
            "resource_name": resource.name,
            "resource_id": str(resource.id),
            "dataset_id": str(resource.dataset.id),
            "dataset_title": resource.dataset.title,
            "updated_fields": updated_fields or {},
        },
    )


def track_resource_deleted(
    user: User,
    resource_id: str,
    resource_name: str,
    dataset_id: str,
    dataset_title: str,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a resource is deleted.
    Since the resource is deleted, we need to pass its ID and name separately.
    """
    # For deleted objects, we can't pass the model instance directly
    # Instead, we create a dictionary with the relevant information
    extra_data = {
        "resource_name": resource_name,
        "resource_id": resource_id,
        "dataset_id": dataset_id,
        "dataset_title": dataset_title,
        "action": "deleted",
    }

    # If we have the dataset, we can use it as the target
    target = None
    if dataset_id:
        from api.models.Dataset import Dataset

        try:
            target = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            pass

    # Record the activity
    from authorization.activity import record_activity

    record_activity(
        actor=user,
        verb="deleted",
        action_object=None,  # No action object since it's deleted
        target=target,
        request=request,
        data=extra_data,
    )


def track_resource_downloaded(
    user: User, resource: Resource, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when a resource is downloaded.
    """
    track_model_activity(
        actor=user,
        verb="downloaded",
        model_instance=resource,
        target=resource.dataset,  # The dataset is the target
        request=request,
        extra_data={
            "resource_name": resource.name,
            "resource_id": str(resource.id),
            "resource_type": resource.type,
            "dataset_id": str(resource.dataset.id),
            "dataset_title": resource.dataset.title,
        },
    )


def track_resource_previewed(
    user: User, resource: Resource, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when a resource is previewed.
    """
    track_model_activity(
        actor=user,
        verb="previewed",
        model_instance=resource,
        target=resource.dataset,  # The dataset is the target
        request=request,
        extra_data={
            "resource_name": resource.name,
            "resource_id": str(resource.id),
            "resource_type": resource.type,
            "dataset_id": str(resource.dataset.id),
            "dataset_title": resource.dataset.title,
        },
    )
