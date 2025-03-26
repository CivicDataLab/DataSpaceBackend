import uuid
from typing import TYPE_CHECKING

from django.db import models

from api.utils.file_paths import _chart_image_directory_path

if TYPE_CHECKING:
    from api.models import Dataset


class ResourceChartImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    image = models.ImageField(
        upload_to=_chart_image_directory_path, blank=True, null=True
    )
    dataset = models.ForeignKey(
        "api.Dataset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="chart_images",
    )
    modified = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name

    class Meta:
        db_table = "resource_chart_image"
