import base64
import json
import pickle
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Type,
    TypeVar,
    Union,
    cast,
)

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

JSONValue = Union[Dict[str, Any], List[Any], str, int, float, bool, None]
T = TypeVar("T")


class CustomJSONEncoder(DjangoJSONEncoder):
    """Custom JSON encoder that handles non-standard objects using pickle."""

    def default(self, obj: Any) -> JSONValue:
        """Only serialize non-standard objects using pickle."""
        if isinstance(obj, (dict, list, str, int, float, bool, type(None))):
            return obj  # JSON-compatible values are returned as-is

        # For non-standard objects, serialize using pickle and base64 encoding
        return {
            "_custom_serialized": True,
            "data": base64.b64encode(pickle.dumps(obj)).decode("utf-8"),
        }


class CustomJSONDecoder:
    """Custom JSON decoder that handles pickled objects."""

    @staticmethod
    def decode(value: Any) -> Any:
        """Decode objects that were custom-serialized, otherwise return normal JSON."""
        if isinstance(value, dict) and value.get("_custom_serialized"):
            try:
                return pickle.loads(base64.b64decode(value["data"].encode("utf-8")))
            except (pickle.PickleError, ValueError):
                return value  # Fallback to returning original if decoding fails
        return value


class SerializableJSONField(models.JSONField):
    """JSON field that can handle non-standard Python objects."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.default: Callable[[], Union[Dict[str, Any], List[Any]]] = kwargs.get(
            "default", dict
        )

    def from_db_value(
        self, value: Optional[str], expression: Any, connection: Any
    ) -> Union[Dict[str, Any], List[Any]]:
        """Ensure that deserialized values match their expected types"""
        if value is None:
            return []
        if isinstance(value, str):
            try:
                data = json.loads(value)  # Convert from string to JSON
                decoded_data = self._decode_values(data)
                return decoded_data if isinstance(decoded_data, (list, dict)) else []
            except (json.JSONDecodeError, TypeError):
                return []  # Return empty list if decoding fails
        return cast(Union[Dict[str, Any], List[Any]], value)

    def get_prep_value(self, value: Any) -> Optional[str]:
        """Automatically serialize before saving to database"""
        if value is None:
            return value
        if isinstance(value, str):  # Prevent double encoding
            return value
        return json.dumps(self._encode_values(value), cls=CustomJSONEncoder)

    def _encode_values(self, obj: Any) -> Any:
        """Ensure that only non-JSON serializable objects are encoded"""
        if isinstance(obj, (dict, list, str, int, float, bool, type(None))):
            return obj  # Return JSON-native types as-is
        return CustomJSONEncoder().default(obj)  # Encode non-serializable objects

    def _decode_values(self, obj: Any) -> Any:
        """Ensure proper decoding of serialized objects and remove _custom_serialized fields"""
        if isinstance(obj, dict):
            if "_custom_serialized" in obj and "data" in obj:
                # Deserialize the object and return the decoded value
                return CustomJSONDecoder.decode(obj)

            # Recursively decode and remove _custom_serialized fields from all dictionary items
            return {
                key: self._decode_values(value)
                for key, value in obj.items()
                if key != "_custom_serialized"
            }

        if isinstance(obj, list):
            return [self._decode_values(value) for value in obj]

        if isinstance(obj, str):
            try:
                return self._decode_values(
                    json.loads(obj)
                )  # If it's a JSON string, load it as a Python object
            except json.JSONDecodeError:
                return obj  # Otherwise, return as-is

        return obj  # Return original object if it doesn't match any criteria

    def __getitem__(self, key: str) -> Any:
        """Make the field indexable."""
        if not hasattr(self, "value"):
            raise KeyError(key)
        value = cast(Dict[str, Any], self.value)
        return value[key]

    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """Get a value from the field by key."""
        if not hasattr(self, "value"):
            return default
        value = cast(Dict[str, Any], self.value)
        return value.get(key, default)  # type: ignore
