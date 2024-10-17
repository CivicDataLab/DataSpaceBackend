import re
from django.core.exceptions import ValidationError


def regex_validator(value, pattern):
    if not re.match(pattern, value):
        raise ValidationError(f"Value '{value}' does not match the required pattern.")


def min_length_validator(value, min_length):
    if len(value) < min_length:
        raise ValidationError(f"Value '{value}' must be at least {min_length} characters long.")


VALIDATOR_MAP = {
    'regex_validator': regex_validator,
    'min_length_validator': min_length_validator,
}
