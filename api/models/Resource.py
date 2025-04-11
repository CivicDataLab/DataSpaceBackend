import os
import random
import uuid
from typing import TYPE_CHECKING, Any, Optional

import structlog
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify

logger = structlog.getLogger(__name__)

from api.managers.dvc_manager import DVCManager
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


class ResourceVersion(models.Model):
    resource = models.ForeignKey(
        Resource, on_delete=models.CASCADE, related_name="versions"
    )
    version_number = models.CharField(max_length=50)
    commit_hash = models.CharField(max_length=64, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    change_description = models.TextField(blank=True)

    class Meta:
        unique_together = ("resource", "version_number")
        db_table = "resource_version"


@receiver(post_save, sender=ResourceFileDetails)
def version_resource_with_dvc(sender, instance: ResourceFileDetails, created, **kwargs):
    """Create a new version using DVC when resource is updated"""
    # Initialize DVC manager
    dvc = DVCManager(settings.DVC_REPO_PATH)

    # Skip if this is just being created (first version)
    if created:
        # For first version, we just track it
        try:
            # Use chunked mode for large files (over 100MB)
            file_size = (
                instance.file.size
                if hasattr(instance.file, "size")
                else os.path.getsize(instance.file.path)
            )
            use_chunked = file_size > 100 * 1024 * 1024  # 100MB threshold

            dvc_file = dvc.track_resource(instance.file.path, chunked=use_chunked)
            message = f"Add resource: {instance.resource.name} version {instance.resource.version}"
            dvc.commit_version(dvc_file, message)
            dvc.tag_version(f"{instance.resource.name}-{instance.resource.version}")

            # Create first version record
            ResourceVersion.objects.create(
                resource=instance.resource,
                version_number=instance.resource.version,
                change_description=f"Initial version of {instance.resource.name}",
            )
        except Exception as e:
            logger.error(f"Failed to version resource: {str(e)}")
            # Continue without versioning if it fails
            # This allows the resource to be created even if DVC fails
            pass
    else:
        # For updates, check if the file has actually changed before creating a new version
        try:
            # Skip versioning if the file hasn't changed
            if dvc.verify_file(instance.file.path):
                logger.info(
                    f"No changes detected for {instance.resource.name}, skipping version creation"
                )
                return

            # Determine version number using semantic versioning
            last_version: Optional[ResourceVersion] = (
                instance.resource.versions.order_by("-created_at").first()
            )

            # Handle case when there are no versions yet
            if last_version is None:
                new_version = "v1.0.0"
            else:
                # Default to minor version increment, could be configurable in the future
                new_version = _increment_version(
                    last_version.version_number, increment_type="minor"
                )

            # Use chunked mode for large files (over 100MB)
            file_size = (
                instance.file.size
                if hasattr(instance.file, "size")
                else os.path.getsize(instance.file.path)
            )
            use_chunked = file_size > 100 * 1024 * 1024  # 100MB threshold

            # Update using DVC
            dvc_file = dvc.track_resource(instance.file.path, chunked=use_chunked)
            message = (
                f"Update resource: {instance.resource.name} to version {new_version}"
            )
            dvc.commit_version(dvc_file, message)
            dvc.tag_version(f"{instance.resource.name}-{new_version}")

            # Create version record
            ResourceVersion.objects.create(
                resource=instance.resource,
                version_number=new_version,
                change_description=f"Updated version of {instance.resource.name}",
            )

            # Update resource version field
            instance.resource.version = new_version
            instance.resource.save(update_fields=["version"])

            # Optional: Trigger garbage collection periodically
            # This could be moved to a scheduled task instead
            if random.random() < 0.05:  # 5% chance to run GC on version update
                try:
                    dvc.gc_cache()
                except Exception as e:
                    logger.warning(f"Failed to run garbage collection: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to update resource version: {str(e)}")
            # Continue without versioning if it fails
            pass


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
