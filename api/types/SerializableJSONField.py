import json
import pickle
import base64
from django.db import models
from django.core.serializers.json import DjangoJSONEncoder

class CustomJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        try:
            return super().default(obj)  # Try standard serialization
        except TypeError:
            # Fallback: Serialize non-standard objects using pickle and base64 encoding
            return {
                "_custom_serialized": True,
                "data": base64.b64encode(pickle.dumps(obj)).decode('utf-8'),
            }

class CustomJSONDecoder:
    @staticmethod
    def decode(data):
        if isinstance(data, dict) and data.get("_custom_serialized"):
            return pickle.loads(base64.b64decode(data["data"].encode('utf-8')))
        return data  # If standard JSON, return as-is

class SerializableJSONField(models.JSONField):
    def from_db_value(self, value, expression, connection):
        """Automatically deserialize when retrieving from DB"""
        if value is None:
            return value
        data = json.loads(value)
        return CustomJSONDecoder.decode(data)

    def get_prep_value(self, value):
        """Automatically serialize when saving to DB"""
        if value is None:
            return value
        return json.dumps(value, cls=CustomJSONEncoder)
