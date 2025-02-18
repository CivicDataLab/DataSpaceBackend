import json
import pickle
import base64
from django.db import models
from django.core.serializers.json import DjangoJSONEncoder

class CustomJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        """Only serialize non-standard objects using pickle"""
        if isinstance(obj, (dict, list, str, int, float, bool, type(None))):
            return obj  # JSON-compatible values are returned as-is

        # For non-standard objects, serialize using pickle and base64 encoding
        return {
            "_custom_serialized": True,
            "data": base64.b64encode(pickle.dumps(obj)).decode('utf-8'),
        }

class CustomJSONDecoder:
    @staticmethod
    def decode(value):
        """Decode objects that were custom-serialized, otherwise return normal JSON"""
        if isinstance(value, dict) and value.get("_custom_serialized"):
            try:
                return pickle.loads(base64.b64decode(value["data"].encode('utf-8')))
            except (pickle.PickleError, ValueError):
                return value  # Fallback to returning original if decoding fails
        return value

class SerializableJSONField(models.JSONField):
    def from_db_value(self, value, expression, connection):
        """Automatically deserialize from database"""
        if value is None:
            return value
        if isinstance(value, str):
            try:
                data = json.loads(value)  # Convert from string to JSON
                return self._decode_values(data)
            except (json.JSONDecodeError, TypeError):
                return value  # If already deserialized, return as-is
        return value  # If it's already a Python object, return as-is

    def get_prep_value(self, value):
        """Automatically serialize before saving to database"""
        if value is None:
            return value
        if isinstance(value, str):  # Prevent double encoding
            return value
        return json.dumps(self._encode_values(value), cls=CustomJSONEncoder)

    def _encode_values(self, obj):
        """Ensure that only non-JSON serializable objects are encoded"""
        if isinstance(obj, (dict, list, str, int, float, bool, type(None))):
            return obj  # Return JSON-native types as-is
        return CustomJSONEncoder().default(obj)  # Encode non-serializable objects

    def _decode_values(self, obj):
        """Ensure proper decoding of serialized objects"""
        if isinstance(obj, dict):
            return {key: self._decode_values(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self._decode_values(value) for value in obj]
        return CustomJSONDecoder.decode(obj)  # Decode non-serializable objects
