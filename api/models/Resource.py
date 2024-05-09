import uuid

from django.db import models

from api.enums import DataType
from api.models import Dataset


class Resource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=True, blank=True, related_name='resources')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    type = models.CharField(max_length=50, choices=DataType.choices, default=DataType.FILE, blank=False, unique=False)
    name = models.CharField(max_length=50, unique=False, blank=True)


class ResourceFileDetails(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, null=False, blank=False)
    file = models.FileField(upload_to='resources/')
    size = models.FloatField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
