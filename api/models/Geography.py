from typing import Optional

from django.db import models

from api.utils.enums import GeoTypes


class Geography(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=75, unique=True)
    code = models.CharField(
        max_length=100, null=True, blank=True, unique=False, default=""
    )
    type = models.CharField(max_length=20, choices=GeoTypes.choices)
    parent_id = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, default=None
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"

    class Meta:
        db_table = "geography"
        verbose_name_plural = "geographies"
        ordering = ["name"]
