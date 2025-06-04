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


def format_integrity_error(
    error: IntegrityError,
) -> Dict[str, Union[Dict[str, List[str]], List[str]]]:
    """
    Formats Django IntegrityError into a consistent GraphQL error format with field-specific messages
    """
    error_str = str(error)

    # Handle value too long errors
    if "value too long for type character varying" in error_str:
        # Try to extract field name from the error message
        # Error format: 'value too long for type character varying(1000) for column "description"'
        import re

        field_match = re.search(r'column "([^"]+)"', error_str)
        length_match = re.search(r"varying\(([0-9]+)\)", error_str)

        field = field_match.group(1) if field_match else "field"
        max_length = length_match.group(1) if length_match else "N"

        return {
            "field_errors": {
                field: [f"This field cannot be longer than {max_length} characters."]
            }
        }

    # Handle other integrity errors with a more user-friendly message
    return {
        "non_field_errors": [
            "A database constraint was violated. Please check your input."
        ]
    }


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
