import uuid

from django.db import models

from api.enums import GeoTypes


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=75, unique=True, null=False, blank=False)
    description = models.CharField(max_length=1000, null=True, blank=True)
    parent_id = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
