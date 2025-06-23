"""Registry for activity tracking handlers."""

# mypy: disable-error-code=arg-type

from typing import Any, Callable, Dict, Optional, Type

from django.db.models import Model
from django.http import HttpRequest

from authorization.models import User

# Type for handler functions
HandlerFunction = Callable[[User, Model, Optional[Dict[str, Any]], HttpRequest], None]

# Registry of model handlers
# Structure: {
#     'ModelName': {
#         'verb': handler_function,
#         ...
#     },
#     ...
# }
MODEL_HANDLERS: Dict[str, Dict[str, HandlerFunction]] = {}


def register_model_handler(
    model_name: str, verb: str, handler: HandlerFunction
) -> None:
    """
    Register a handler function for a specific model and verb.

    Args:
        model_name: The name of the model class (e.g., 'Dataset')
        verb: The verb to handle (e.g., 'created', 'updated')
        handler: The handler function to call
    """
    if model_name not in MODEL_HANDLERS:
        MODEL_HANDLERS[model_name] = {}

    MODEL_HANDLERS[model_name][verb] = handler


def get_handler(model_name: str, verb: str) -> Optional[HandlerFunction]:
    """
    Get the handler function for a specific model and verb.

    Args:
        model_name: The name of the model class
        verb: The verb to handle

    Returns:
        The handler function if found, None otherwise
    """
    if model_name in MODEL_HANDLERS and verb in MODEL_HANDLERS[model_name]:
        return MODEL_HANDLERS[model_name][verb]
    return None


def handle_activity(
    model_name: str,
    verb: str,
    user: User,
    instance: Model,
    data: Optional[Dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
) -> bool:
    """
    Handle an activity for a specific model and verb.

    Args:
        model_name: The name of the model class
        verb: The verb to handle
        user: The user performing the action
        instance: The model instance
        data: Additional data for the activity
        request: The current HTTP request

    Returns:
        True if the activity was handled, False otherwise
    """
    handler = get_handler(model_name, verb)
    if handler:
        handler(user, instance, data, request)
        return True
    return False


# Import all handlers to register them
from api.activities.registry_handlers import *  # noqa
