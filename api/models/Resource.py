import uuid
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from api.utils.enums import DataType

if TYPE_CHECKING:
    from api.models.Dataset import Dataset

User = get_user_model()


class Resource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(
        "api.Dataset",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name="resources",
    )

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    type = models.CharField(
        max_length=50,
        choices=DataType.choices,
        default=DataType.FILE,
        blank=False,
        unique=False,
    )
    name = models.CharField(max_length=200, unique=False, blank=False)
    description = models.TextField(blank=True, null=True)
    slug = models.SlugField(max_length=255, unique=True)
    url = models.URLField(max_length=500)
    is_active = models.BooleanField(default=True)
    preview_enabled = models.BooleanField(default=False)
    preview_details = models.OneToOneField(
        "api.ResourcePreviewDetails", on_delete=models.CASCADE, null=True, blank=True
    )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"


class ResourceFileDetails(models.Model):
    resource = models.OneToOneField(
        Resource, on_delete=models.CASCADE, null=False, blank=False
    )
    file = models.FileField(upload_to="resources/")
    size = models.FloatField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    format = models.CharField(max_length=50)


class ResourcePreviewDetails(models.Model):
    is_all_entries = models.BooleanField(default=True)
    start_entry = models.IntegerField(default=0)
    end_entry = models.IntegerField(default=10)


class ResourceDataTable(models.Model):
    """Model to store indexed CSV data for a resource."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.OneToOneField(
        Resource, on_delete=models.CASCADE, null=False, blank=False
    )
    table_name = models.CharField(max_length=255, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "resource_data_table"
        ordering = ["-modified"]

    def __str__(self):
        return f"{self.resource.name} - {self.table_name}"

    def save(self, *args, **kwargs):
        if not self.table_name:
            # Generate a unique table name based on resource ID
            self.table_name = f"resource_data_{self.resource.id.hex}"
        super().save(*args, **kwargs)
