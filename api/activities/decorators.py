import functools
from typing import Any, Callable, Optional, TypeVar, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Model
from django.http import HttpRequest

from authorization.activity import record_activity
from authorization.consent import UserConsent

User = get_user_model()
F = TypeVar("F", bound=Callable[..., Any])


def track_activity(
    verb: str,
    get_actor: Optional[Callable] = None,
    get_action_object: Optional[Callable] = None,
    get_target: Optional[Callable] = None,
    get_data: Optional[Callable] = None,
) -> Callable[[F], F]:
    """
    Decorator to track activities in view functions.

    Args:
        verb: The verb describing the activity (e.g., 'viewed', 'downloaded')
        get_actor: Function to extract the actor from the view arguments
        get_action_object: Function to extract the action object from the view arguments
        get_target: Function to extract the target from the view arguments
        get_data: Function to extract additional data from the view arguments

    Returns:
        Decorated function that tracks the activity
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract request from args (typically the first or second argument in view functions)
            request = None
            for arg in list(args) + list(kwargs.values()):
                if isinstance(arg, HttpRequest):
                    request = arg
                    break

            # If no request was found, we can't check consent
            if not request:
                return func(*args, **kwargs)

            # Get the actor (default to the authenticated user)
            actor = None
            if get_actor:
                actor = get_actor(*args, **kwargs)
            elif hasattr(request, "user") and request.user.is_authenticated:
                actor = request.user

            # If no actor, we can't track the activity
            if not actor:
                return func(*args, **kwargs)

            # Get consent settings
            require_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
                "REQUIRE_CONSENT", True
            )

            # If consent is not required, we can skip the consent check
            if not require_consent:
                # Just call the function and track the activity afterward
                result = func(*args, **kwargs)

                # Get the action object and target
                action_object = (
                    get_action_object(*args, **kwargs) if get_action_object else None
                )
                target = get_target(*args, **kwargs) if get_target else None

                # Get additional data
                data = get_data(*args, **kwargs) if get_data else {}

                # Record the activity
                record_activity(
                    actor=actor,
                    verb=verb,
                    action_object=action_object,
                    target=target,
                    request=request,
                    data=data,
                )

                return result

            # If consent is required, check if the user has given consent
            try:
                consent = UserConsent.objects.get(user=actor)
                if not consent.activity_tracking_enabled:
                    # User hasn't given consent, just call the function without tracking
                    return func(*args, **kwargs)
            except UserConsent.DoesNotExist:
                # No consent record, check default consent setting
                default_consent = getattr(settings, "ACTIVITY_CONSENT", {}).get(
                    "DEFAULT_CONSENT", False
                )
                if not default_consent:
                    # Default is no consent, just call the function without tracking
                    return func(*args, **kwargs)
                # Create a consent record with the default setting
                UserConsent.objects.get_or_create(
                    user=actor, defaults={"activity_tracking_enabled": default_consent}
                )

            # Get the action object and target
            action_object = (
                get_action_object(*args, **kwargs) if get_action_object else None
            )
            target = get_target(*args, **kwargs) if get_target else None

            # Get additional data
            data = get_data(*args, **kwargs) if get_data else {}

            # Call the function first
            result = func(*args, **kwargs)

            # Record the activity after the function has been called
            # This ensures we only track successful actions
            record_activity(
                actor=actor,
                verb=verb,
                action_object=action_object,
                target=target,
                request=request,
                data=data,
            )

            return result

        return cast(F, wrapper)

    return decorator
