from typing import TYPE_CHECKING

from django.db import models

from api.models.Metadata import BaseMetadata

if TYPE_CHECKING:
    from api.models.Collaborative import Collaborative


class CollaborativeMetadata(BaseMetadata):
    collaborative = models.ForeignKey(
        "api.Collaborative",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="metadata",
    )

    def __str__(self) -> str:
        return f"{self.collaborative.title} - {self.metadata_item.label}"

    class Meta(BaseMetadata.Meta):
        db_table = "collaborative_metadata"
        unique_together = ("collaborative", "metadata_item")
