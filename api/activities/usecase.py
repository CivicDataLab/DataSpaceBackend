from typing import Any, Dict, Optional

from django.http import HttpRequest

from api.activities.base import track_model_activity
from api.models.UseCase import UseCase
from authorization.models import User


def track_usecase_created(
    user: User, usecase: UseCase, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when a use case is created.
    """
    track_model_activity(
        actor=user,
        verb="created",
        model_instance=usecase,
        target=usecase.organization if usecase.organization else None,
        request=request,
        extra_data={
            "usecase_title": usecase.title,
            "usecase_id": str(usecase.id),
            "organization_id": (
                str(usecase.organization.id) if usecase.organization else None
            ),
            "organization_name": (
                usecase.organization.name if usecase.organization else None
            ),
        },
    )


def track_usecase_updated(
    user: User,
    usecase: UseCase,
    updated_fields: Optional[Dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a use case is updated.

    Args:
        user: The user performing the update
        usecase: The use case being updated
        updated_fields: Dictionary of fields that were updated
        request: The current HTTP request
    """
    track_model_activity(
        actor=user,
        verb="updated",
        model_instance=usecase,
        target=usecase.organization if usecase.organization else None,
        request=request,
        extra_data={
            "usecase_title": usecase.title,
            "usecase_id": str(usecase.id),
            "updated_fields": updated_fields or {},
        },
    )


def track_usecase_published(
    user: User, usecase: UseCase, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when a use case is published (status changed to PUBLISHED).
    """
    track_model_activity(
        actor=user,
        verb="published",
        model_instance=usecase,
        target=usecase.organization if usecase.organization else None,
        request=request,
        extra_data={
            "usecase_title": usecase.title,
            "usecase_id": str(usecase.id),
        },
    )


def track_usecase_deleted(
    user: User,
    usecase_id: str,
    usecase_title: str,
    organization_id: Optional[str] = None,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a use case is deleted.
    Since the use case is deleted, we need to pass its ID and title separately.
    """
    # For deleted objects, we can't pass the model instance directly
    # Instead, we create a dictionary with the relevant information
    extra_data = {
        "usecase_title": usecase_title,
        "usecase_id": usecase_id,
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


def track_dataset_added_to_usecase(
    user: User,
    usecase: UseCase,
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
            model_instance=usecase,
            target=dataset,
            request=request,
            extra_data={
                "usecase_title": usecase.title,
                "usecase_id": str(usecase.id),
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
            model_instance=usecase,
            request=request,
            extra_data={
                "usecase_title": usecase.title,
                "usecase_id": str(usecase.id),
                "dataset_id": dataset_id,
                "dataset_title": dataset_title,
            },
        )


def track_dataset_removed_from_usecase(
    user: User,
    usecase: UseCase,
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
            model_instance=usecase,
            target=dataset,
            request=request,
            extra_data={
                "usecase_title": usecase.title,
                "usecase_id": str(usecase.id),
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
            model_instance=usecase,
            request=request,
            extra_data={
                "usecase_title": usecase.title,
                "usecase_id": str(usecase.id),
                "dataset_id": dataset_id,
                "dataset_title": dataset_title,
            },
        )
