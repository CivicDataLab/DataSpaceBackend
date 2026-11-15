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
from api.services.query_engine.profile_views import MAX_DETAIL_COLUMNS

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


class ScopeOnlySerializer(serializers.Serializer):
    scope = ScopeField()


class ResourceProfileRequestSerializer(serializers.Serializer):
    scope = ScopeField()
    columns = serializers.ListField(
        child=serializers.CharField(max_length=255, trim_whitespace=False),
        required=False,
        max_length=MAX_DETAIL_COLUMNS,
    )


class QueryBodyField(serializers.DictField):
    """The query body: a JSON object with a valid-length ``scope`` (the spec is checked later)."""

    def to_internal_value(self, data: Any) -> Dict[str, Any]:
        value = super().to_internal_value(data)
        scope = value.get("scope")
        if not isinstance(scope, str) or not scope or len(scope) > SCOPE_MAX_LENGTH:
            raise serializers.ValidationError("scope is required", code="scope")
        return dict(value)


class QueryRequestSerializer(serializers.Serializer):
    body = QueryBodyField()


class SearchRequestSerializer(serializers.Serializer):
    scope = ScopeField()
    query = serializers.CharField(min_length=1, max_length=500)
    size = serializers.IntegerField(min_value=1, max_value=10, default=5)
    geographies = serializers.ListField(
        child=serializers.CharField(max_length=75), required=False, max_length=10, default=list
    )
    year_from = serializers.IntegerField(min_value=1900, max_value=2100, required=False)
    year_to = serializers.IntegerField(min_value=1900, max_value=2100, required=False)

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if data.get("year_from") and data.get("year_to") and data["year_from"] > data["year_to"]:
            raise serializers.ValidationError({"year_from": "after year_to"}, code="year_range")
        return data


class PendingSummariesSerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=20, default=10)


class SummaryWriteSerializer(serializers.Serializer):
    facts_hash = serializers.CharField(min_length=64, max_length=64)
    text = serializers.CharField(max_length=5000, trim_whitespace=True)
    model = serializers.CharField(max_length=200)
    prompt_version = serializers.CharField(max_length=64)
