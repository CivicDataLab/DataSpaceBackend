from typing import TYPE_CHECKING

from django.db import models

from api.models.Metadata import BaseMetadata

if TYPE_CHECKING:
    from api.models.Resource import Resource


class ResourceMetadata(BaseMetadata):
    resource = models.ForeignKey(
        "api.Resource", on_delete=models.CASCADE, related_name="metadata_items"
    )
    # Override the value field to use JSONField instead of CharField
    value = models.JSONField()  # type: ignore

    def __str__(self) -> str:
        return f"{self.resource.name} - {self.metadata_item.label}"

    class Meta(BaseMetadata.Meta):
        db_table = "resource_metadata"
        unique_together = ("resource", "metadata_item")
