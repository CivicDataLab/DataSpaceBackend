from django.db import models

from api.models import Metadata, Resource


class ResourceMetadata(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, null=False, blank=False)
    metadata_item = models.ForeignKey(Metadata, on_delete=models.CASCADE, null=False, blank=False)
    value = models.CharField(max_length=1000, unique=False)
