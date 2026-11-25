"""The worker that moves processing requests through DOST-Catalyst.

One ``step()``:

1. checks each RUNNING row once: stores the outputs of a finished job, stops a
   job an administrator cancelled, or fails a job that ran too long;
2. starts at most one REQUESTED row, when the global switch is on.

All state is in the database, so a restarted worker carries on where it
stopped, and several workers never take the same row (``skip_locked``).
``manage.py run_document_processing`` calls ``step()`` in a loop.
"""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Any, Optional

import structlog
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from api.models import ProcessedFile, ResourceProcessing
from api.services.catalyst_client import (
    CatalystBusy,
    CatalystClient,
    CatalystError,
    CatalystJobLost,
)
from api.services.document_processing import ProcessingOptions, processing_enabled
from api.utils.enums import ProcessedFileKind, ProcessingStatus

logger = structlog.get_logger("dataspace.document_worker")

# Envelope output formats that become ProcessedFile rows.
OUTPUT_KINDS = {
    "dost_tables_md": ProcessedFileKind.TABLES_MD,
    "dost_sentences_csv": ProcessedFileKind.SENTENCES_CSV,
    "dost_problems_csv": ProcessedFileKind.PROBLEMS_CSV,
    "dost_images_zip": ProcessedFileKind.IMAGES_ZIP,
}
SUCCESS = frozenset({"success", "partial_success"})

# A RUNNING row without a job ID this old lost its worker before Catalyst
# answered; it goes back to REQUESTED (the idempotency key avoids a second job).
ORPHAN_AFTER = timedelta(minutes=10)


def idempotency_key(processing: ResourceProcessing) -> str:
    """Same key for retries of one request, a new key for a new request."""
    return f"dataspace-{processing.id}-{int(processing.requested_at.timestamp())}"


@dataclass
class DocumentWorker:
    client: CatalystClient
    max_wait: timedelta

    @classmethod
    def from_settings(cls) -> "DocumentWorker":
        return cls(
            client=CatalystClient.from_settings(),
            max_wait=timedelta(minutes=settings.CATALYST_MAX_WAIT_MINUTES),
        )

    def step(self) -> bool:
        """Do one round of work; True when something changed."""
        changed = False
        running = ResourceProcessing.objects.filter(status=ProcessingStatus.RUNNING)
        for pk in running.values_list("pk", flat=True):
            changed |= self._advance(pk)
        if processing_enabled():
            changed |= self._start_next()
        return changed

    def _claim(self) -> Optional[ResourceProcessing]:
        with transaction.atomic():
            processing = (
                ResourceProcessing.objects.select_for_update(skip_locked=True)
                .filter(status=ProcessingStatus.REQUESTED)
                .order_by("requested_at")
                .first()
            )
            if processing is None:
                return None
            processing.status = ProcessingStatus.RUNNING
            processing.started_at = timezone.now()
            processing.save(update_fields=["status", "started_at"])
            return processing

    def _start_next(self) -> bool:
        processing = self._claim()
        if processing is None:
            return False
        log = logger.bind(processing=str(processing.id), resource=str(processing.resource_id))
        try:
            details = processing.resource.resourcefiledetails
        except ObjectDoesNotExist:
            self._finish(processing, ProcessingStatus.FAILED, error="The resource has no file.")
            return True
        options = ProcessingOptions.from_stored(processing.options)
        try:
            with details.file.open("rb") as content:
                job_id = self.client.submit(
                    PurePosixPath(details.file.name).name,
                    content,
                    options.catalyst_request(),
                    idempotency_key(processing),
                )
        except CatalystBusy as exc:
            log.warning("catalyst_busy_requeue", error=str(exc))
            processing.status = ProcessingStatus.REQUESTED
            processing.started_at = None
            processing.save(update_fields=["status", "started_at"])
            return False
        except (CatalystError, OSError) as exc:
            log.error("catalyst_submit_failed", error=str(exc))
            self._finish(processing, ProcessingStatus.FAILED, error=str(exc))
            return True
        processing.catalyst_job_id = job_id
        processing.source_sha256 = details.sha256 or ""
        processing.save(update_fields=["catalyst_job_id", "source_sha256"])
        log.info("catalyst_job_started", job_id=job_id)
        return True

    def _advance(self, pk: Any) -> bool:
        with transaction.atomic():
            processing = (
                ResourceProcessing.objects.select_for_update(skip_locked=True)
                .filter(pk=pk, status=ProcessingStatus.RUNNING)
                .first()
            )
            if processing is None:  # another worker has it, or it changed
                return False
            return self._advance_locked(processing)

    def _advance_locked(self, processing: ResourceProcessing) -> bool:
        log = logger.bind(processing=str(processing.id), job_id=processing.catalyst_job_id)
        if not processing.catalyst_job_id:
            if processing.cancel_requested:
                self._finish(processing, ProcessingStatus.CANCELLED)
                return True
            if processing.started_at and timezone.now() - processing.started_at > ORPHAN_AFTER:
                processing.status = ProcessingStatus.REQUESTED
                processing.started_at = None
                processing.save(update_fields=["status", "started_at"])
                return True
            return False
        job_id = processing.catalyst_job_id
        if processing.cancel_requested:
            self._delete_job(job_id)
            self._finish(processing, ProcessingStatus.CANCELLED)
            log.info("catalyst_job_cancelled")
            return True
        try:
            status = self.client.status(job_id)
        except CatalystJobLost:
            self._finish(
                processing,
                ProcessingStatus.FAILED,
                error="Catalyst lost the job, for example after a restart. Process it again.",
            )
            return True
        except CatalystError as exc:  # also CatalystBusy: try again next round
            log.warning("catalyst_status_unavailable", error=str(exc))
            return False
        if status.get("state") != "done":
            if processing.started_at and timezone.now() - processing.started_at > self.max_wait:
                self._delete_job(job_id)
                minutes = int(self.max_wait.total_seconds() // 60)
                self._finish(
                    processing,
                    ProcessingStatus.FAILED,
                    error=f"Catalyst did not finish within {minutes} minutes.",
                )
                return True
            return False
        self._store_result(processing, status)
        self._delete_job(job_id)
        return True

    def _store_result(self, processing: ResourceProcessing, status: dict[str, Any]) -> None:
        envelope = status.get("envelope") or {}
        outcome = envelope.get("status")
        if outcome not in SUCCESS:
            messages = [e.get("message", "") for e in envelope.get("errors") or []]
            error = (
                "; ".join(m for m in messages if m)
                or status.get("error")
                or (f"Catalyst could not process the document ({outcome or 'no result'}).")
            )
            self._finish(processing, ProcessingStatus.FAILED, error=error)
            return
        try:
            downloads = [
                (OUTPUT_KINDS[item["format"]], item["filename"], self.client.download(item["url"]))
                for item in envelope.get("outputs") or []
                if item.get("format") in OUTPUT_KINDS
            ]
        except CatalystError as exc:
            self._finish(processing, ProcessingStatus.FAILED, error=f"Download failed: {exc}")
            return
        # Each old row removes its S3 object in a post_delete signal.
        processing.files.all().delete()
        for kind, filename, data in downloads:
            processed = ProcessedFile(processing=processing, kind=kind, size=len(data))
            processed.file.save(filename, ContentFile(data), save=False)
            processed.save()
        processing.report = envelope.get("dost")
        self._finish(processing, ProcessingStatus.DONE)

    def _finish(self, processing: ResourceProcessing, status: str, error: str = "") -> None:
        processing.status = status
        processing.error = error
        processing.finished_at = timezone.now()
        processing.cancel_requested = False
        processing.save()

    def _delete_job(self, job_id: str) -> None:
        try:
            self.client.delete(job_id)
        except CatalystError as exc:  # Catalyst deletes its files later anyway
            logger.warning("catalyst_delete_failed", job_id=job_id, error=str(exc))
