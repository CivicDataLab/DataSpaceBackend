import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from django.db import models
from django.utils.text import slugify

from api.models.SerializableJSONField import SerializableJSONField
from api.utils.enums import ChartStatus, ChartTypes

if TYPE_CHECKING:
    from api.models.Resource import Resource


class ResourceChartDetails(models.Model):
    """Model for storing chart details associated with a resource."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.ForeignKey(
        "api.Resource", on_delete=models.CASCADE, null=False, blank=False
    )
    name = models.CharField(max_length=50, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    chart_type = models.CharField(
        max_length=50,
        choices=ChartTypes.choices,
        default=ChartTypes.BAR,
        blank=False,
        unique=False,
    )
    options = SerializableJSONField(blank=True, default=dict)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    filters = SerializableJSONField(blank=True, null=True, default=list)
    status = models.CharField(
        max_length=50,
        choices=ChartStatus.choices,
        default=ChartStatus.DRAFT,
        blank=False,
        unique=False,
    )

    def __str__(self) -> str:
        """Return a string representation of the model."""
        return f"{self.resource.name} - {self.chart_type}"

    class Meta:
        """Meta options for ResourceChartDetails."""

        db_table = "resource_chart_details"
        ordering = ["-created"]
