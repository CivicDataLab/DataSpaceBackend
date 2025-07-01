import re
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    TypedDict,
    TypeGuard,
    TypeVar,
    Union,
    cast,
)

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.utils import DataError
from strawberry.types import ExecutionContext


class FieldErrors(TypedDict):
    field_errors: Dict[str, List[str]]


class NonFieldErrors(TypedDict):
    non_field_errors: List[str]


ErrorDictType = Union[FieldErrors, NonFieldErrors]

# Custom type for field errors
FieldErrorType = Dict[str, Union[str, List[str]]]

F = TypeVar("F", bound=Callable[..., Any])


def is_field_errors(error_data: ErrorDictType) -> TypeGuard[FieldErrors]:
    return "field_errors" in error_data


def is_non_field_errors(error_data: ErrorDictType) -> TypeGuard[NonFieldErrors]:
    return "non_field_errors" in error_data


def convert_error_dict(
    error_data: ErrorDictType,
) -> Dict[str, Union[Dict[str, List[str]], List[str]]]:
    """Convert TypedDict error format to format expected by format_errors"""
    if is_field_errors(error_data):
        return {"field_errors": error_data["field_errors"]}
    elif is_non_field_errors(error_data):
        return {"non_field_errors": error_data["non_field_errors"]}
    return {}


def format_validation_error(
    error: DjangoValidationError,
) -> ErrorDictType:
    """Formats Django ValidationError into a consistent GraphQL error format with field-specific messages"""
    error_str = str(error)

    # Try to extract field name from validation error message

    patterns = [
        # Pattern for "Value for 'Field Name' must be..."
        r"Value for '([^']+)' must be",
        # Pattern for "Invalid value: '...' for 'Field Name'. Must be one of..."
        r"Invalid value: '[^']+' for '([^']+)'. Must be one of",
        # Pattern for "Invalid values: ... for 'Field Name'. Must be one of..."
        r"Invalid values: [^']+ for '([^']+)'. Must be one of",
        # Pattern for "Required value not sent for: Field Name"
        r"Required value not sent for: ([^']+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, error_str)
        if match:
            field_name = match.group(1).lower().replace(" ", "_")
            return FieldErrors(field_errors={field_name: [error_str]})

    # If no specific format matched, return as non-field error
    return NonFieldErrors(non_field_errors=[error_str])


def format_integrity_error(e: IntegrityError) -> ErrorDictType:
    """Format a Django IntegrityError into a dictionary of field errors."""
    error_str = str(e)

    # Check if field name is provided in the error
    if ":" in error_str:
        field_name, error_msg = error_str.split(":", 1)
        # Try to extract max length from error message
        import re

        match = re.search(
            r"value too long for type character varying\((\d+)\)", error_msg
        )
        if match:
            max_length = match.group(1)
            return FieldErrors(
                field_errors={
                    field_name: [
                        f"This field cannot be longer than {max_length} characters."
                    ]
                }
            )
        # Other field-specific errors
        return FieldErrors(field_errors={field_name: [error_msg.strip()]})

    # Try to extract field name and max length from error message
    match = re.search(r"value too long for type character varying\((\d+)\)", error_str)
    if match:
        max_length = match.group(1)
        return FieldErrors(
            field_errors={
                "value": [f"This field cannot be longer than {max_length} characters."]
            }
        )

    # If no specific format matched, return as non-field error
    return NonFieldErrors(non_field_errors=[error_str])


def format_data_error(
    error: DataError,
) -> ErrorDictType:
    """
    Formats Django DataError into a consistent GraphQL error format with field-specific messages
    """
    error_str = str(error)

    # Try to extract field name and max length from error message
    import re

    match = re.search(r"value too long for type character varying\((\d+)\)", error_str)
    if match:
        max_length = match.group(1)
        return FieldErrors(
            field_errors={
                "value": [f"This field cannot be longer than {max_length} characters."]
            }
        )

    # If no specific format matched, return as non-field error
    return NonFieldErrors(non_field_errors=[error_str])


def handle_django_errors(func: F) -> F:
    """
    Decorator to handle Django errors in GraphQL mutations

    Args:
        func: The function to decorate

    Returns:
        The decorated function

    Raises:
        None

    Notes:
        When a Django error is caught, the error is stored in the context
        and the function returns None. Callers should check for None returns.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Optional[Any]:
        try:
            return func(*args, **kwargs)
        except DjangoValidationError as e:
            error_data = format_validation_error(e)
            # Get the info object from args (usually the second argument in mutations)
            info = next(
                (arg for arg in args if isinstance(arg, ExecutionContext)), None
            )
            if info:
                info.context.validation_errors = error_data
            return None
        except (DataError, IntegrityError) as e:
            error_data = (
                format_data_error(e)
                if isinstance(e, DataError)
                else format_integrity_error(e)
            )
            info = next(
                (arg for arg in args if isinstance(arg, ExecutionContext)), None
            )
            if info:
                info.context.validation_errors = error_data
            return None

    return cast(F, wrapper)
