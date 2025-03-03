from typing import Optional

from django.db import models

from api.utils.enums import (
    MetadataDataTypes,
    MetadataModels,
    MetadataStandards,
    MetadataTypes,
)


class Metadata(models.Model):
    id = models.AutoField(primary_key=True)
    label = models.CharField(max_length=75, unique=False)
    data_standard = models.CharField(
        max_length=50,
        choices=MetadataStandards.choices,
        blank=True,
        unique=False,
        null=True,
    )
    urn = models.CharField(max_length=175, unique=True, blank=True)
    data_type = models.CharField(
        max_length=50, choices=MetadataDataTypes.choices, blank=False, unique=False
    )
    options = models.JSONField(blank=True, null=True)  # for select and multiselect
    validator = models.JSONField(blank=True, default=list)  # predefined set
    validator_options = models.JSONField(
        blank=True, null=True
    )  # options for validation
    type = models.CharField(
        max_length=50, choices=MetadataTypes.choices, blank=False, unique=False
    )
    model = models.CharField(
        max_length=50, choices=MetadataModels.choices, blank=False, unique=False
    )
    enabled = models.BooleanField(default=False)
    filterable = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.label} ({self.data_type})"

    class Meta:
        db_table = "metadata"
        ordering = ["label"]
