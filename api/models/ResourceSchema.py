from django.db import models

from api.utls.enums import FieldTypes
from api.models import Resource


class ResourceSchema(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, null=False, blank=False)
    field_name = models.CharField(max_length=255, null=False, blank=False)
    format = models.CharField(max_length=255, null=False, blank=False, choices=FieldTypes.choices)
    description = models.CharField(max_length=1000, null=True, blank=True)
