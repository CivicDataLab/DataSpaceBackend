import uuid

from django.db import models

from api.utils.file_paths import _chart_image_directory_path


class ResourceChartImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=False, blank=True)
    description = models.CharField(max_length=1000, unique=False, blank=True)
    image = models.ImageField(upload_to=_chart_image_directory_path, blank=True, null=True)
