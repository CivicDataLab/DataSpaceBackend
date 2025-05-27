from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.db.models import Model
from django.http import HttpRequest

from authorization.activity import record_activity

# Get the User model and create a type alias for type checking
User = get_user_model()


def track_model_activity(
    actor: User,
    verb: str,
    model_instance: Model,
    target: Optional[Model] = None,
    request: Optional[HttpRequest] = None,
    extra_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Track activity for a model instance.

    Args:
        actor: The user performing the action
        verb: The action being performed (e.g., 'created', 'updated', 'deleted')
        model_instance: The model instance being acted upon
        target: Optional target of the action (e.g., a dataset is the target when a resource is created)
        request: The current HTTP request (used for consent checking)
        extra_data: Additional data to store with the activity
    """
    # Create a descriptive action object
    action_object = model_instance

    # Record the activity with the user's consent check
    record_activity(
        actor=actor,
        verb=verb,
        action_object=action_object,
        target=target,
        request=request,
        data=extra_data or {},
    )
