from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from api.models.Metadata import Metadata
    from api.models.Resource import Resource


class ResourceMetadata(models.Model):
    id = models.AutoField(primary_key=True)
    resource = models.ForeignKey(
        "api.Resource", on_delete=models.CASCADE, related_name="metadata_items"
    )
    metadata_item = models.ForeignKey(
        "api.Metadata", on_delete=models.CASCADE, related_name="resource_metadata"
    )
    value = models.JSONField()
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.resource.name} - {self.metadata_item.label}"

    class Meta:
        db_table = "resource_metadata"
        unique_together = ("resource", "metadata_item")
        ordering = ["metadata_item__label"]
