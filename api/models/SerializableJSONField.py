import json
import pickle
import base64
from django.db import models
from django.core.serializers.json import DjangoJSONEncoder

class CustomJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        """Only serialize non-standard objects using pickle"""
        if isinstance(obj, (dict, list, str, int, float, bool, type(None))):
            return obj  # Return standard JSON objects as-is
        return {
            "_custom_serialized": True,
            "data": base64.b64encode(pickle.dumps(obj)).decode('utf-8'),
        }

class CustomJSONDecoder:
    @staticmethod
    def decode(value):
        """Decode objects that were custom-serialized, otherwise return normal JSON"""
        if isinstance(value, dict) and value.get("_custom_serialized"):
            return pickle.loads(base64.b64decode(value["data"].encode('utf-8')))
        return value

class SerializableJSONField(models.JSONField):
    def from_db_value(self, value, expression, connection):
        """Automatically deserialize from database"""
        if value is None:
            return value
        try:
            data = json.loads(value)  # Convert from string to JSON
            return CustomJSONDecoder.decode(data)
        except (json.JSONDecodeError, TypeError):
            return value  # If already deserialized, return as-is

    def get_prep_value(self, value):
        """Automatically serialize before saving to database"""
        if value is None:
            return value
        try:
            return json.dumps(value, cls=CustomJSONEncoder)  # Convert to JSON string
        except TypeError:
            return json.dumps({"_custom_serialized": True, "data": base64.b64encode(pickle.dumps(value)).decode('utf-8')})
