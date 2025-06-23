from typing import Any, Dict, List, Optional, TypeVar, Union

from actstream.models import Action  # type: ignore
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model, Q, QuerySet
from django.http import HttpRequest

# Type aliases for mypy
User = get_user_model()

# mypy: disable-error-code=valid-type
# mypy: disable-error-code=misc
# mypy: disable-error-code=no-any-return
# mypy: disable-error-code=name-defined


def get_user_activity_stream(
    user: User, request: Optional[HttpRequest] = None, limit: int = 20
) -> QuerySet:
    """
    Get the activity stream for a specific user, respecting consent settings.

    Args:
        user: The user whose activity stream to retrieve
        request: The current HTTP request (for consent checking)
        limit: Maximum number of activities to return

    Returns:
        QuerySet of Action objects
    """
    from actstream.models import actor_stream

    # Get consent settings
    require_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
        "REQUIRE_CONSENT", True
    )

    # If consent is not required, we can return the activity stream directly
    if not require_consent:
        return actor_stream(user)[:limit]

    # If consent is required, check if the user has given consent
    if request and hasattr(request, "has_activity_consent"):
        if not request.has_activity_consent:
            # Return an empty queryset if the user hasn't given consent
            return Action.objects.none()

    # Get the user's activity stream
    return actor_stream(user)[:limit]


def get_object_activity_stream(
    obj: Model, request: Optional[HttpRequest] = None, limit: int = 20
) -> QuerySet:
    """
    Get the activity stream for a specific object (e.g., a dataset or organization).

    Args:
        obj: The object whose activity stream to retrieve
        request: The current HTTP request (for consent checking)
        limit: Maximum number of activities to return

    Returns:
        QuerySet of Action objects
    """
    from actstream.models import action_object_stream

    # Get consent settings
    require_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
        "REQUIRE_CONSENT", True
    )

    # If consent is not required, we can return the activity stream directly
    if not require_consent:
        return action_object_stream(obj)[:limit]

    # If consent is required, check if the user has given consent
    if request and hasattr(request, "has_activity_consent"):
        if not request.has_activity_consent:
            # Return an empty queryset if the user hasn't given consent
            return Action.objects.none()

    # Get the object's activity stream
    return action_object_stream(obj)[:limit]


def get_target_activity_stream(
    obj: Model, request: Optional[HttpRequest] = None, limit: int = 20
) -> QuerySet:
    """
    Get the activity stream where the specified object is the target.

    Args:
        obj: The target object whose activity stream to retrieve
        request: The current HTTP request (for consent checking)
        limit: Maximum number of activities to return

    Returns:
        QuerySet of Action objects
    """
    from actstream.models import target_stream

    # Get consent settings
    require_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
        "REQUIRE_CONSENT", True
    )

    # If consent is not required, we can return the activity stream directly
    if not require_consent:
        return target_stream(obj)[:limit]

    # If consent is required, check if the user has given consent
    if request and hasattr(request, "has_activity_consent"):
        if not request.has_activity_consent:
            # Return an empty queryset if the user hasn't given consent
            return Action.objects.none()

    # Get the target's activity stream
    return target_stream(obj)[:limit]


def get_combined_activity_stream(
    request: Optional[HttpRequest] = None, limit: int = 20
) -> QuerySet:
    """
    Get a combined activity stream for the entire application.

    Args:
        request: The current HTTP request (for consent checking)
        limit: Maximum number of activities to return

    Returns:
        QuerySet of Action objects
    """
    from actstream.models import Action

    # Get consent settings
    require_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
        "REQUIRE_CONSENT", True
    )

    # If consent is not required, we can return the activity stream directly
    if not require_consent:
        return Action.objects.all().order_by("-timestamp")[:limit]

    # If consent is required, check if the user has given consent
    if request and hasattr(request, "has_activity_consent"):
        if not request.has_activity_consent:
            # Return an empty queryset if the user hasn't given consent
            return Action.objects.none()

    # Get the combined activity stream
    return Action.objects.all().order_by("-timestamp")[:limit]


def get_organization_activity_stream(
    organization_id: str, request: Optional[HttpRequest] = None, limit: int = 20
) -> QuerySet:
    """
    Get the activity stream for a specific organization, including activities where the organization
    is the actor, action object, or target.

    Args:
        organization_id: The ID of the organization
        request: The current HTTP request (for consent checking)
        limit: Maximum number of activities to return

    Returns:
        QuerySet of Action objects
    """
    from actstream.models import Action

    from api.models.Organization import Organization

    # Get consent settings
    require_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
        "REQUIRE_CONSENT", True
    )

    # If consent is required, check if the user has given consent
    if require_consent:
        if request and hasattr(request, "has_activity_consent"):
            if not request.has_activity_consent:
                # Return an empty queryset if the user hasn't given consent
                return Action.objects.none()

    try:
        organization = Organization.objects.get(id=organization_id)
        org_content_type = ContentType.objects.get_for_model(Organization)

        # Get activities where the organization is the actor, action object, or target
        return Action.objects.filter(
            Q(actor_content_type=org_content_type, actor_object_id=organization.id)
            | Q(
                action_object_content_type=org_content_type,
                action_object_object_id=organization.id,
            )
            | Q(target_content_type=org_content_type, target_object_id=organization.id)
        ).order_by("-timestamp")[:limit]
    except Organization.DoesNotExist:
        return Action.objects.none()


def format_activity_for_display(action: Action) -> Dict:
    """
    Format an activity action for display in the UI.

    Args:
        action: The Action object to format

    Returns:
        Dictionary with formatted activity data
    """
    # Get the actor, action object, and target (if they exist)
    actor = action.actor
    action_object = action.action_object
    target = action.target

    # Format the activity data
    activity_data = {
        "id": action.id,
        "timestamp": action.timestamp,
        "verb": action.verb,
        "actor": {
            "id": actor.id if hasattr(actor, "id") else None,
            "name": str(actor),
            "type": actor.__class__.__name__,
        },
        "action_object": None,
        "target": None,
        "data": action.data,
    }

    # Add action object data if it exists
    if action_object:
        activity_data["action_object"] = {
            "id": action_object.id if hasattr(action_object, "id") else None,
            "name": str(action_object),
            "type": action_object.__class__.__name__,
        }

    # Add target data if it exists
    if target:
        activity_data["target"] = {
            "id": target.id if hasattr(target, "id") else None,
            "name": str(target),
            "type": target.__class__.__name__,
        }

    return activity_data


def format_activity_stream_for_display(actions: QuerySet) -> List[Dict[str, Any]]:
    """
    Format a queryset of activity actions for display in the UI.

    Args:
        actions: QuerySet of Action objects

    Returns:
        List of dictionaries with formatted activity data
    """
    return [format_activity_for_display(action) for action in actions]
