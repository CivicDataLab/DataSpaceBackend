"""Request shapes for the internal query-engine endpoints, and reading them.

Every endpoint validates its query string or body through one of these before
anything else runs. ``read_input`` turns a failure into a 400 that names the
bad fields and their error codes ("required", "max_length", …), never the
values sent.

Docs: ./architecture.md
"""

from typing import Any, Dict, Type

from rest_framework import serializers

from api.services.query_engine.errors import BadRequest

SCOPE_MAX_LENGTH = 64


def read_input(serializer_class: Type[serializers.Serializer], data: Any) -> Dict[str, Any]:
    """The validated data, or BadRequest listing each bad field's error codes."""
    serializer = serializer_class(data=data)
    if serializer.is_valid():
        return dict(serializer.validated_data)
    fields = {
        name: sorted({getattr(error, "code", "invalid") for error in _flatten(errors)})
        for name, errors in serializer.errors.items()
    }
    raise BadRequest(
        f"Invalid fields: {', '.join(sorted(fields))}.",
        details={"fields": fields},
        reason="invalid_input",
        fields=sorted(fields),
    )


def _flatten(errors: Any) -> list:
    if isinstance(errors, dict):
        return [e for value in errors.values() for e in _flatten(value)]
    if isinstance(errors, list):
        return [e for value in errors for e in _flatten(value)]
    return [errors]


class ScopeField(serializers.CharField):
    """The scope string; its shape is checked by parse_scope (400 ``bad_scope``)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(max_length=SCOPE_MAX_LENGTH, trim_whitespace=False, **kwargs)


class ScopeRequestSerializer(serializers.Serializer):
    scope = ScopeField()
    include_dataset_ids = serializers.BooleanField(required=False, default=False)
