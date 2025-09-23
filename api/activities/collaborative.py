from typing import Any, Dict, Optional

from django.http import HttpRequest

from api.activities.base import track_model_activity
from api.models.Collaborative import Collaborative
from authorization.models import User


def track_collaborative_created(
    user: User, collaborative: Collaborative, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when a collaborative is created.
    """
    track_model_activity(
        actor=user,
        verb="created",
        model_instance=collaborative,
        target=collaborative.organization if collaborative.organization else None,
        request=request,
        extra_data={
            "collaborative_title": collaborative.title,
            "collaborative_id": str(collaborative.id),
            "organization_id": (
                str(collaborative.organization.id)
                if collaborative.organization
                else None
            ),
            "organization_name": (
                collaborative.organization.name if collaborative.organization else None
            ),
        },
    )


def track_collaborative_updated(
    user: User,
    collaborative: Collaborative,
    updated_fields: Optional[Dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a collaborative is updated.

    Args:
        user: The user performing the update
        collaborative: The collaborative being updated
        updated_fields: Dictionary of fields that were updated
        request: The current HTTP request
    """
    track_model_activity(
        actor=user,
        verb="updated",
        model_instance=collaborative,
        target=collaborative.organization if collaborative.organization else None,
        request=request,
        extra_data={
            "collaborative_title": collaborative.title,
            "collaborative_id": str(collaborative.id),
            "updated_fields": updated_fields or {},
        },
    )


def track_collaborative_published(
    user: User, collaborative: Collaborative, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when a collaborative is published (status changed to PUBLISHED).
    """
    track_model_activity(
        actor=user,
        verb="published",
        model_instance=collaborative,
        target=collaborative.organization if collaborative.organization else None,
        request=request,
        extra_data={
            "collaborative_title": collaborative.title,
            "collaborative_id": str(collaborative.id),
        },
    )


def track_collaborative_deleted(
    user: User,
    collaborative_id: str,
    collaborative_title: str,
    organization_id: Optional[str] = None,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a collaborative is deleted.
    Since the collaborative is deleted, we need to pass its ID and title separately.
    """
    # For deleted objects, we can't pass the model instance directly
    # Instead, we create a dictionary with the relevant information
    extra_data = {
        "collaborative_title": collaborative_title,
        "collaborative_id": collaborative_id,
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


def track_dataset_added_to_collaborative(
    user: User,
    collaborative: Collaborative,
    dataset_id: str,
    dataset_title: str,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a dataset is added to a use case.
    """
    from api.models.Dataset import Dataset

    try:
        dataset = Dataset.objects.get(id=dataset_id)
        track_model_activity(
            actor=user,
            verb="added dataset to",
            model_instance=collaborative,
            target=dataset,
            request=request,
            extra_data={
                "collaborative_title": collaborative.title,
                "collaborative_id": str(collaborative.id),
                "dataset_id": dataset_id,
                "dataset_title": dataset_title,
            },
        )
    except Dataset.DoesNotExist:
        # If the dataset doesn't exist, we still want to track the activity
        # but we can't use the dataset as the target
        track_model_activity(
            actor=user,
            verb="added dataset to",
            model_instance=collaborative,
            request=request,
            extra_data={
                "collaborative_title": collaborative.title,
                "collaborative_id": str(collaborative.id),
                "dataset_id": dataset_id,
                "dataset_title": dataset_title,
            },
        )


def track_dataset_removed_from_collaborative(
    user: User,
    collaborative: Collaborative,
    dataset_id: str,
    dataset_title: str,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a dataset is removed from a use case.
    """
    from api.models.Dataset import Dataset

    try:
        dataset = Dataset.objects.get(id=dataset_id)
        track_model_activity(
            actor=user,
            verb="removed dataset from",
            model_instance=collaborative,
            target=dataset,
            request=request,
            extra_data={
                "collaborative_title": collaborative.title,
                "collaborative_id": str(collaborative.id),
                "dataset_id": dataset_id,
                "dataset_title": dataset_title,
            },
        )
    except Dataset.DoesNotExist:
        # If the dataset doesn't exist, we still want to track the activity
        # but we can't use the dataset as the target
        track_model_activity(
            actor=user,
            verb="removed dataset from",
            model_instance=collaborative,
            request=request,
            extra_data={
                "collaborative_title": collaborative.title,
                "collaborative_id": str(collaborative.id),
                "dataset_id": dataset_id,
                "dataset_title": dataset_title,
            },
        )
