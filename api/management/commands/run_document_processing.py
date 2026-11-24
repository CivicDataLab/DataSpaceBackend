"""Run the DOST-Catalyst document processing worker.

    python manage.py run_document_processing          # loop until stopped
    python manage.py run_document_processing --once   # one round, then exit

The worker only acts on requests that an administrator made; see
``api.services.document_worker``.
"""

import time
from typing import Any

import structlog
from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from api.services.document_worker import DocumentWorker

logger = structlog.get_logger("dataspace.document_worker")


class Command(BaseCommand):
    help = "Send processing requests to DOST-Catalyst and store the outputs."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="Do one round, then exit.")

    def handle(self, *args: Any, **options: Any) -> None:
        worker = DocumentWorker.from_settings()
        if not settings.DOCUMENT_PROCESSING_ENABLED:
            logger.warning(
                "document_processing_disabled",
                detail="New requests are not started; running jobs are still followed.",
            )
        if options["once"]:
            worker.step()
            return
        logger.info("document_worker_started", catalyst_url=settings.CATALYST_URL)
        while True:
            try:
                changed = worker.step()
            except Exception:  # one bad round must not stop the worker
                logger.exception("document_worker_round_failed")
                changed = False
            if not changed:
                time.sleep(settings.CATALYST_POLL_SECONDS)
