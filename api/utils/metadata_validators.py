import re
from typing import Any, Dict

from django.core.exceptions import ValidationError


def regex_validator(value: Any, pattern: str) -> None:
    if not re.match(pattern, value):
        raise ValidationError(f"Value '{value}' does not match the required pattern.")


def min_length_validator(value: Any, min_length: int) -> None:
    if len(value) < min_length:
        raise ValidationError(
            f"Value '{value}' must be at least {min_length} characters long."
        )


def validate_metadata_value(value: Any) -> bool:
    """
    Validate if the metadata value is of a supported type
    """
    supported_types = (str, int, float, bool, list, dict)
    return isinstance(value, supported_types)


def validate_metadata_dict(metadata: Dict[str, Any]) -> bool:
    """
    Validate if all values in the metadata dictionary are of supported types
    """
    return all(validate_metadata_value(value) for value in metadata.values())


VALIDATOR_MAP = {
    "regex_validator": regex_validator,
    "min_length_validator": min_length_validator,
}
