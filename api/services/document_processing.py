"""Rules for asking DOST-Catalyst to process a resource file.

Processing never starts by itself. A resource gets a REQUESTED row only when
all of these hold:

* ``DOCUMENT_PROCESSING_ENABLED`` is True (the global switch, off by default);
* the user is a superuser (the Keycloak realm role ``admin``);
* the resource has a file in a format that Catalyst processes (PDF);
* the resource is not already waiting for or in a Catalyst job.

The Django admin actions call these functions; the worker
(``manage.py run_document_processing``) does the Catalyst work.
"""

import re
from dataclasses import asdict, dataclass
from typing import Any, Optional

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.utils import timezone

from api.models import Resource, ResourceFileDetails, ResourceProcessing
from api.utils.enums import ProcessingStatus

# ``ResourceFileDetails.format`` values that Catalyst can process.
PROCESSABLE_FORMATS = frozenset({"PDF"})

# Sarvam language codes look like "hi-IN" or "en-IN".
_LANGUAGE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}$")

ALREADY_ACTIVE = "The resource is already waiting for or in processing."


class ProcessingRefused(Exception):
    """The request breaks one of the rules; the message says which, for the user."""


@dataclass(frozen=True)
class ProcessingOptions:
    """What an administrator may choose for one run; stored as ``options``.

    ``use_sarvam`` costs money and sends page images to Sarvam, so it is off
    unless asked for. ``language`` is a Sarvam code and applies only to Sarvam.
    """

    full_page_ocr: bool = False
    use_sarvam: bool = False
    language: Optional[str] = None

    @classmethod
    def from_stored(cls, stored: dict[str, Any]) -> "ProcessingOptions":
        return cls(
            full_page_ocr=bool(stored.get("full_page_ocr", False)),
            use_sarvam=bool(stored.get("use_sarvam", False)),
            language=stored.get("language") or None,
        )

    def validated(self) -> "ProcessingOptions":
        if self.language and not _LANGUAGE.match(self.language):
            raise ProcessingRefused(
                f"'{self.language}' is not a language code such as hi-IN or en-IN."
            )
        if self.language and not self.use_sarvam:
            raise ProcessingRefused("A language can be chosen only with Sarvam OCR.")
        return self

    def catalyst_request(self) -> dict[str, Any]:
        """The Catalyst ``options`` form field (a ConvertRequest) for this run."""
        request: dict[str, Any] = {"dost": {"enabled": True}}
        ocr: dict[str, Any] = {}
        if self.full_page_ocr:
            ocr["mode"] = "full_page"
        if self.use_sarvam:
            ocr["__variant__"] = "SarvamOcrOptions"
            if self.language:
                ocr["lang"] = [self.language]
                request["dost"]["source_language"] = self.language
        if ocr:
            request["formats"] = {"pdf": {"pipeline_options": {"ocr_options": ocr}}}
        return request


def processing_enabled() -> bool:
    return bool(settings.DOCUMENT_PROCESSING_ENABLED)


def can_request_processing(user: Any) -> bool:
    """True when this user may ask for processing at all (switch on, superuser)."""
    return processing_enabled() and bool(user.is_superuser)


def _file_details(resource: Resource) -> Optional[ResourceFileDetails]:
    try:
        return resource.resourcefiledetails
    except ObjectDoesNotExist:
        return None


def _check(resource: Resource, user: Any) -> ResourceFileDetails:
    """Raise ProcessingRefused unless the resource may be processed now."""
    if not processing_enabled():
        raise ProcessingRefused("Document processing is switched off.")
    if not user.is_superuser:
        raise ProcessingRefused("Only an administrator can process documents.")
    details = _file_details(resource)
    if details is None or not details.file:
        raise ProcessingRefused("The resource has no file.")
    file_format = (details.format or "").upper()
    if file_format not in PROCESSABLE_FORMATS:
        raise ProcessingRefused(
            f"Only PDF files can be processed; this file is {file_format or 'of unknown format'}."
        )
    return details


def request_processing(
    resource: Resource, user: Any, options: Optional[ProcessingOptions] = None
) -> ResourceProcessing:
    """Mark the resource REQUESTED for the worker, or raise ProcessingRefused.

    A finished, failed or cancelled earlier request is reset; its output files
    stay until the new run replaces them.
    """
    details = _check(resource, user)
    chosen = (options or ProcessingOptions()).validated()
    with transaction.atomic():
        existing = ResourceProcessing.objects.select_for_update().filter(resource=resource).first()
        if existing is not None and existing.is_active:
            raise ProcessingRefused(ALREADY_ACTIVE)
        values = {
            "status": ProcessingStatus.REQUESTED,
            "options": asdict(chosen),
            "requested_by": user,
            "requested_at": timezone.now(),
            "started_at": None,
            "finished_at": None,
            "catalyst_job_id": "",
            "cancel_requested": False,
            "error": "",
            "report": None,
            "source_sha256": details.sha256 or "",
        }
        if existing is not None:
            for field, value in values.items():
                setattr(existing, field, value)
            existing.save()
            return existing
        try:
            with transaction.atomic():
                return ResourceProcessing.objects.create(resource=resource, **values)
        except IntegrityError as exc:  # a second request created the row first
            raise ProcessingRefused(ALREADY_ACTIVE) from exc


def cancel_processing(processing: ResourceProcessing, user: Any) -> ResourceProcessing:
    """Cancel a waiting request now, or ask the worker to stop a running job.

    A running job keeps the status RUNNING until the worker has told Catalyst
    to stop; then the worker sets CANCELLED.
    """
    if not user.is_superuser:
        raise ProcessingRefused("Only an administrator can cancel processing.")
    with transaction.atomic():
        current = ResourceProcessing.objects.select_for_update().get(pk=processing.pk)
        if current.status == ProcessingStatus.REQUESTED:
            current.status = ProcessingStatus.CANCELLED
            current.finished_at = timezone.now()
            current.save(update_fields=["status", "finished_at"])
        elif current.status == ProcessingStatus.RUNNING:
            current.cancel_requested = True
            current.save(update_fields=["cancel_requested"])
        else:
            raise ProcessingRefused(f"Nothing to cancel: the status is {current.status}.")
    return current
