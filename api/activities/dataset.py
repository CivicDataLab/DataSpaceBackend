from typing import Any, Dict, Optional

from django.http import HttpRequest

from api.activities.base import track_model_activity
from api.models.Dataset import Dataset
from authorization.models import User


def track_dataset_created(
    user: User, dataset: Dataset, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when a dataset is created.
    """
    track_model_activity(
        actor=user,
        verb="created",
        model_instance=dataset,
        target=dataset.organization if dataset.organization else None,
        request=request,
        extra_data={
            "dataset_title": dataset.title,
            "dataset_id": str(dataset.id),
            "access_type": dataset.access_type,
        },
    )


def track_dataset_updated(
    user: User,
    dataset: Dataset,
    updated_fields: Optional[Dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a dataset is updated.

    Args:
        user: The user performing the update
        dataset: The dataset being updated
        updated_fields: Dictionary of fields that were updated
        request: The current HTTP request
    """
    track_model_activity(
        actor=user,
        verb="updated",
        model_instance=dataset,
        target=dataset.organization if dataset.organization else None,
        request=request,
        extra_data={
            "dataset_title": dataset.title,
            "dataset_id": str(dataset.id),
            "updated_fields": updated_fields or {},
        },
    )


def track_dataset_published(
    user: User, dataset: Dataset, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when a dataset is published (status changed to PUBLISHED).
    """
    track_model_activity(
        actor=user,
        verb="published",
        model_instance=dataset,
        target=dataset.organization if dataset.organization else None,
        request=request,
        extra_data={
            "dataset_title": dataset.title,
            "dataset_id": str(dataset.id),
        },
    )


def track_dataset_deleted(
    user: User,
    dataset_id: str,
    dataset_title: str,
    organization_id: Optional[str] = None,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a dataset is deleted.
    Since the dataset is deleted, we need to pass its ID and title separately.
    """
    # For deleted objects, we can't pass the model instance directly
    # Instead, we create a dictionary with the relevant information
    extra_data = {
        "dataset_title": dataset_title,
        "dataset_id": dataset_id,
        "action": "deleted",
    }

    # If we have the organization, we can use it as the target
    target = None
    if organization_id:
        from api.models.Organization import Organization

        try:
            target = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
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
