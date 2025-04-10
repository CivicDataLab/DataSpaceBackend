from typing import TYPE_CHECKING

from django.db import models

from api.models.Metadata import BaseMetadata

if TYPE_CHECKING:
    from api.models.UseCase import UseCase


class UseCaseMetadata(BaseMetadata):
    usecase = models.ForeignKey(
        "api.UseCase",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="metadata",
    )

    def __str__(self) -> str:
        return f"{self.usecase.title} - {self.metadata_item.label}"

    class Meta(BaseMetadata.Meta):
        db_table = "usecase_metadata"
        unique_together = ("usecase", "metadata_item")
