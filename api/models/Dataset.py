from django.db import models
import uuid

from api.models import Organization


class Tag(models.Model):
    value = models.CharField(max_length=50, unique=True, blank=False)


class Dataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(Tag, blank=True)
