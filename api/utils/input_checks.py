"""Checks for mutation input that the database or model would not catch (#292).

Each function returns a fixed message for the client, or None when the value is
fine, so every resolver can raise it with the error type it already uses.
Mutations save without `full_clean`, so URLField, choices and similar model
rules are never applied on their own.
"""

import datetime
from typing import Iterable, Optional, Sequence

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Model

API_TIMEOUT_RANGE = (1, 600)


def too_long_error(
    model: type[Model], field: str, value: Optional[str], label: str
) -> Optional[str]:
    """Message when `value` is longer than the column, instead of Postgres' own text."""
    max_length = getattr(model._meta.get_field(field), "max_length", None)
    if value and max_length and len(value) > max_length:
        return f"{label} cannot be longer than {max_length} characters."
    return None


def url_error(
    value: Optional[str], label: str, schemes: Optional[Sequence[str]] = None
) -> Optional[str]:
    """Message when a non-empty value is not a URL (empty clears the field)."""
    if not value:
        return None
    try:
        URLValidator(schemes=schemes)(value)
    except ValidationError:
        return f"{label} must be a valid URL."
    return None


def range_error(
    value: Optional[int], label: str, minimum: int, maximum: Optional[int] = None
) -> Optional[str]:
    if value is None:
        return None
    if maximum is None and value < minimum:
        return f"{label} must be at least {minimum}."
    if maximum is not None and not minimum <= value <= maximum:
        return f"{label} must be between {minimum} and {maximum}."
    return None


def date_order_error(
    started_on: Optional[datetime.date], completed_on: Optional[datetime.date]
) -> Optional[str]:
    if started_on and completed_on and completed_on < started_on:
        return "Completion date cannot be before the start date."
    return None


def whitespace_error(value: Optional[str], label: str) -> Optional[str]:
    """Message when a value contains whitespace (spaces, tabs, newlines)."""
    if value and any(character.isspace() for character in value):
        return f"{label} cannot contain spaces."
    return None


def blank_error(value: Optional[str], saved: Optional[str], label: str) -> Optional[str]:
    """Message when a blank or whitespace-only value would replace a saved non-blank one.

    A row that is already blank may be sent back as it is: editors resend the whole
    form on every change, so refusing it would block every other edit of that row.
    """
    # Not a string = left out of the input (None or strawberry's UNSET): nothing changes
    if not isinstance(value, str) or value.strip() or not (saved or "").strip():
        return None
    return f"{label} cannot be blank."


def choice_error(value: Optional[str], choices: Iterable[str], label: str) -> Optional[str]:
    """Message when a non-empty value is not one of `choices` (empty clears the field)."""
    allowed = list(choices)
    if value and value not in allowed:
        return f"{label} must be one of: {', '.join(allowed)}."
    return None
