from typing import Any, Dict, Optional, Type, TypeVar, Union

from actstream.actions import action
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from django.http import HttpRequest

# mypy: disable-error-code=no-any-return


def record_activity(
    actor: Union[AbstractBaseUser, Model],
    verb: str,
    action_object: Optional[Model] = None,
    target: Optional[Model] = None,
    request: Optional[HttpRequest] = None,
    **kwargs: Any
) -> Optional[Model]:
    """
    Record an activity based on settings and user consent.
    This function wraps the actstream.actions.action function and adds consent checking.

    Args:
        actor: The actor performing the activity (usually a user)
        verb: The verb describing the activity (e.g., 'created', 'updated')
        action_object: The object being acted upon
        target: The target of the activity
        request: The current request object (used to check consent)
        **kwargs: Additional arguments to pass to the action function

    Returns:
        The created Action instance or None if consent was not given
    """
    # Get consent settings
    require_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
        "REQUIRE_CONSENT", True
    )
    track_anonymous = getattr(settings, "ACTIVITY_CONSENT", {}).get(
        "TRACK_ANONYMOUS", False
    )

    # If consent is not required, we can record the activity without checking consent
    if not require_consent:
        # For anonymous users (when actor is not a user model), check track_anonymous setting
        if not hasattr(actor, "is_authenticated"):
            if not track_anonymous:
                return None
        return action(
            actor=actor, verb=verb, action_object=action_object, target=target, **kwargs
        )

    # If consent is required, check if we have consent
    # Check if we have a request and if the user has given consent
    if request and hasattr(request, "has_activity_consent"):
        if not request.has_activity_consent:
            return None

    # If we don't have a request, we need to check the actor's consent directly
    # This is useful for background tasks where there is no request
    elif hasattr(actor, "activity_consent"):
        try:
            if not actor.activity_consent.activity_tracking_enabled:
                return None
        except Exception:
            # If there's any error checking consent, don't record the activity
            return None
    # If we can't determine consent, default to not recording the activity when consent is required
    else:
        return None

    # Record the activity
    return action(
        actor=actor, verb=verb, action_object=action_object, target=target, **kwargs
    )
