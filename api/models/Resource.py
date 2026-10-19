import hashlib
import uuid
from typing import TYPE_CHECKING, Any, Optional

import structlog
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils.text import slugify

logger = structlog.getLogger(__name__)

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
    download_count = models.IntegerField(default=0)
    version = models.CharField(max_length=50, default="v1.0")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Resource.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"


class ResourceFileDetails(models.Model):
    resource = models.OneToOneField(Resource, on_delete=models.CASCADE, null=False, blank=False)
    file = models.FileField(upload_to="resources/", max_length=300)
    size = models.FloatField(blank=True, null=True)
    sha256 = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="SHA-256 of the file contents, computed when the file is saved.",
    )
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
    resource = models.OneToOneField(Resource, on_delete=models.CASCADE, null=False, blank=False)
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
            safe_name = slugify(self.resource.name)[:50]
            safe_title = slugify(self.resource.dataset.title)[:50]
            resource_id = self.resource.id.hex[:8]  # Use shorter ID
            self.table_name = f"{safe_name}_{safe_title}_{resource_id}"
        super().save(*args, **kwargs)


class ResourceVersion(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="versions")
    version_number = models.CharField(max_length=50)
    commit_hash = models.CharField(max_length=64, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    change_description = models.TextField(blank=True)

    class Meta:
        unique_together = ("resource", "version_number")
        db_table = "resource_version"


def compute_sha256(fieldfile: Any) -> Optional[str]:
    """Stream the file once and return its SHA-256 hex digest, or None if unreadable.

    Works both for a file already in storage and for an upload that has not
    been written yet (the position is reset afterwards so the write still
    starts at byte 0).
    """
    if not fieldfile:
        return None
    digest = hashlib.sha256()
    try:
        fieldfile.open("rb")
        for chunk in fieldfile.chunks():
            digest.update(chunk)
        fieldfile.seek(0)
    except Exception as exc:  # a missing or unreadable file must never block a save
        logger.warning(f"Could not hash resource file {getattr(fieldfile, 'name', '')}: {exc}")
        return None
    return digest.hexdigest()


@receiver(pre_save, sender=ResourceFileDetails)
def hash_resource_file(sender, instance: ResourceFileDetails, **kwargs):
    """Keep ``sha256`` in step with the file. Recomputed only when the file changes."""
    if not instance.file:
        instance.sha256 = None
        return
    if instance.pk and instance.sha256:
        stored_name = (
            ResourceFileDetails.objects.filter(pk=instance.pk)
            .values_list("file", flat=True)
            .first()
        )
        if stored_name == instance.file.name:
            return  # same file as before
    instance.sha256 = compute_sha256(instance.file)


def _increment_version(version: str, increment_type: str = "minor") -> str:
    """Semantic version incrementing logic

    Args:
        version: Current version string (e.g., "v1.0.0")
        increment_type: One of "major", "minor", or "patch"

    Returns:
        New version string
    """
    if version.startswith("v"):
        version = version[1:]

    parts = version.split(".")
    if len(parts) < 3:
        parts = parts + ["0"] * (3 - len(parts))

    major, minor, patch = map(int, parts)

    if increment_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif increment_type == "minor":
        minor += 1
        patch = 0
    else:  # patch
        patch += 1

    return f"v{major}.{minor}.{patch}"
