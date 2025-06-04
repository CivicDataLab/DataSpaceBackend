from functools import wraps
from typing import Any, Callable, Dict, List, Mapping, Optional, TypeVar, Union, cast

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from strawberry.types import ExecutionContext

# Custom type for field errors
FieldErrorType = Dict[str, Union[str, List[str]]]
ErrorDictType = Dict[str, List[FieldErrorType]]


def format_validation_error(
    error: ValidationError,
) -> Mapping[str, Union[Dict[str, List[str]], List[str]]]:
    """
    Formats Django ValidationError into a consistent GraphQL error format
    """
    if hasattr(error, "message_dict"):
        # Handle model validation errors
        field_errors: Dict[str, List[str]] = {}
        for field, messages in error.message_dict.items():
            if isinstance(messages, (list, tuple)):
                field_errors[field] = list(map(str, messages))
            else:
                field_errors[field] = [str(messages)]
        return {"field_errors": field_errors}
    else:
        # Handle non-field validation errors
        return {"non_field_errors": [str(error)]}


def format_integrity_error(error: IntegrityError) -> Dict[str, List[str]]:
    """
    Formats Django IntegrityError into a consistent GraphQL error format
    """
    return {"non_field_errors": [str(error)]}


F = TypeVar("F", bound=Callable[..., Any])


def handle_django_errors(func: F) -> F:
    """
    Decorator to handle Django errors in GraphQL mutations
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Optional[Any]:
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            error_data = format_validation_error(e)
            # Get the info object from args (usually the second argument in mutations)
            info = next(
                (arg for arg in args if isinstance(arg, ExecutionContext)), None
            )
            if info:
                info.context.validation_errors = error_data
            return None
        except IntegrityError as e:
            error_data = format_integrity_error(e)
            info = next(
                (arg for arg in args if isinstance(arg, ExecutionContext)), None
            )
            if info:
                info.context.validation_errors = error_data
            return None

    return cast(F, wrapper)
