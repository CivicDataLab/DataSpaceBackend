import uuid

from django.db import models

from api.utls.enums import AccessTypes
from api.models import Organization, Dataset, Resource, ResourceSchema


class AccessModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=300, unique=False, blank=True, null=True)
    description = models.CharField(max_length=1000, unique=False, blank=True, null=True)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=False, blank=False)
    type = models.CharField(max_length=100, unique=False, blank=False, choices=AccessTypes.choices,
                            default=AccessTypes.PUBLIC)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)


class AccessModelResource(models.Model):
    access_model = models.ForeignKey(AccessModel, on_delete=models.CASCADE, null=False, blank=False)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, null=False, blank=False)
    fields = models.ManyToManyField(ResourceSchema)
