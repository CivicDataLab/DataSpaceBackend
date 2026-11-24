"""DOST-Catalyst processing of a resource file, and the files it gives back.

A row exists only after an administrator asks for processing; an upload never
creates one. The worker (``manage.py run_document_processing``) sends the file
to Catalyst and stores the outputs here.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from api.utils.enums import ProcessedFileKind, ProcessingStatus
from api.utils.file_paths import _processed_file_directory_path
from api.utils.storage import private_storage

# A resource in one of these states is waiting for, or in, a Catalyst job.
ACTIVE_STATUSES = frozenset({ProcessingStatus.REQUESTED, ProcessingStatus.RUNNING})


class ResourceProcessing(models.Model):
    """The latest processing request of one resource: one row per resource."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.OneToOneField(
        "api.Resource", on_delete=models.CASCADE, related_name="processing"
    )
    status = models.CharField(
        max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.REQUESTED
    )
    options = models.JSONField(
        default=dict, blank=True, help_text="Catalyst request options, e.g. the OCR language."
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    requested_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    catalyst_job_id = models.CharField(max_length=64, blank=True)
    cancel_requested = models.BooleanField(
        default=False, help_text="An administrator asked to stop the running job."
    )
    error = models.TextField(blank=True)
    report = models.JSONField(
        null=True, blank=True, help_text="The DOST extraction report that Catalyst returns."
    )
    source_sha256 = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 of the resource file that was processed; another hash means stale.",
    )

    class Meta:
        db_table = "resource_processing"

    def __str__(self) -> str:
        return f"{self.resource} - {self.status}"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def is_stale(self) -> bool:
        """True when the resource file changed after it was processed."""
        if self.status != ProcessingStatus.DONE or not self.source_sha256:
            return False
        try:
            current = self.resource.resourcefiledetails.sha256
        except ObjectDoesNotExist:  # the file was removed after processing
            return True
        return current != self.source_sha256


class ProcessedFile(models.Model):
    """One output file of a processing run, stored privately next to the resource files."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    processing = models.ForeignKey(
        ResourceProcessing, on_delete=models.CASCADE, related_name="files"
    )
    kind = models.CharField(max_length=20, choices=ProcessedFileKind.choices)
    file = models.FileField(
        upload_to=_processed_file_directory_path, storage=private_storage, max_length=300
    )
    size = models.PositiveBigIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "processed_file"
        constraints = [
            models.UniqueConstraint(
                fields=["processing", "kind"], name="processed_file_one_per_kind"
            )
        ]

    def __str__(self) -> str:
        return f"{self.processing.resource} - {self.kind}"


@receiver(post_delete, sender=ProcessedFile)
def delete_processed_file_from_storage(
    sender: type[ProcessedFile], instance: ProcessedFile, **kwargs: object
) -> None:
    """Remove the S3 object with its row, also when a resource delete cascades."""
    if instance.file:
        instance.file.delete(save=False)
