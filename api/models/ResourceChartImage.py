import uuid

from django.db import models

from api.utils.enums import ChartStatus

# Import the Dataset model indirectly to avoid duplicate import error
from api.utils.file_paths import _chart_image_directory_path


class ResourceChartImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    image = models.ImageField(
        upload_to=_chart_image_directory_path, blank=True, null=True, max_length=300
    )
    dataset = models.ForeignKey(
        "api.Dataset",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="chart_images",
    )
    modified = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=50,
        choices=ChartStatus.choices,
        default=ChartStatus.DRAFT,
        blank=False,
        unique=False,
    )

    def __str__(self) -> str:
        return self.name

    class Meta:
        db_table = "resource_chart_image"
