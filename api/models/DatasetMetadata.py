from django.db import models

from api.models import Dataset, Metadata


class DatasetMetadata(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=False, blank=False, related_name="metadata")
    metadata_item = models.ForeignKey(Metadata, on_delete=models.CASCADE, null=False, blank=False,)
    value = models.CharField(max_length=1000, unique=False)
