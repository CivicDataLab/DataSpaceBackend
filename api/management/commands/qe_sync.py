"""FLOW: ``python manage.py qe_sync`` — keep the query engine's profiles and search index fresh.

Modes:
  --loop               a pass every QE_SYNC_INTERVAL_SECONDS, forever; a pass that
                       finds the lock held is skipped; an error is logged and the
                       next pass runs (the process never crashes on one).
  --once               one pass.
  --reprofile          mark every table for re-profiling (after a Geography reload)
                       and run one pass; the loop finishes the rest.
  --resource-id <id>   one pass that profiles just that table.
  --rebuild-index      write the AI-search index afresh as a new version, then
                       switch the alias to it (a new embedding size needs this).

One-shot modes wait for the lock up to 2 × QE_SYNC_MAX_SECONDS and then exit
non-zero with a clear message — never a silent skip. The loop exits cleanly on
SIGTERM (a container stop), releasing the lock. Runs as its own process
(the ``qe_sync`` compose service / ``qe-sync`` ECS container).

Docs: api/views/query_engine/architecture.md
"""

import signal
import time
import uuid
from typing import Any, Optional

import structlog
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from api.services.query_engine.sync_pass import run_index_rebuild, run_sync_pass
from api.services.query_engine.sync_steps import SyncReport
from api.utils.data_tables import error_fields

logger = structlog.get_logger("dataspace.commands.qe_sync")


class StopRequested(BaseException):
    """The process was told to stop (SIGTERM); not an Exception, so no pass swallows it."""


def _stop_requested(signum: int, frame: Any) -> None:
    raise StopRequested()


class Command(BaseCommand):
    help = "Keep the query engine's table profiles and facts in step with the platform."

    def add_arguments(self, parser: CommandParser) -> None:
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--loop", action="store_true", help="Run a pass every interval.")
        mode.add_argument("--once", action="store_true", help="Run one pass.")
        mode.add_argument("--reprofile", action="store_true", help="Re-profile every table once.")
        mode.add_argument("--resource-id", type=uuid.UUID, help="Profile one table once.")
        mode.add_argument(
            "--rebuild-index",
            action="store_true",
            help="Write the AI-search index afresh as a new version, then switch to it.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # Loop mode: a pass per interval until the process is stopped.
        if options["loop"]:
            self.run_forever()
            return

        # One-shot modes: wait for the lock if another pass holds it, then run.
        wait = 2 * settings.QE_SYNC_MAX_SECONDS
        if options["rebuild_index"]:
            report = run_index_rebuild(lock_wait_seconds=wait)
        else:
            report = run_sync_pass(
                reprofile=bool(options["reprofile"]),
                only_resource_id=options.get("resource_id"),
                lock_wait_seconds=wait,
            )

        # A one-shot run that never got the lock says so and fails.
        if report.skipped:
            raise CommandError("Another qe_sync pass held the lock for too long; nothing ran.")
        self.stdout.write(self.describe(report))

        # Naming one table that then wasn't profiled is a failure, not a quiet success.
        if options.get("resource_id") and not report.profiles.get("profiled"):
            raise CommandError(
                "That table was not profiled: it isn't an active table in the processing set, "
                f"or profiling failed ({report.profiles or 'nothing ran'})."
            )

    def run_forever(self) -> None:
        # Stop cleanly (exit 0) when the container is told to stop, even mid-pass.
        signal.signal(signal.SIGTERM, _stop_requested)
        try:
            while True:
                # One pass; any error is logged and the loop carries on.
                self.run_one_loop_pass()

                # Wait for the next pass.
                time.sleep(settings.QE_SYNC_INTERVAL_SECONDS)
        except StopRequested:
            logger.info("qe_sync_stopped")

    def run_one_loop_pass(self) -> Optional[SyncReport]:
        try:
            return run_sync_pass()
        except Exception as error:
            logger.error("qe_sync_pass_failed", **error_fields(error))
            return None

    @staticmethod
    def describe(report: SyncReport) -> str:
        return (
            f"qe_sync: {report.datasets} datasets, profiles {report.profiles or {}}"
            f"{f' ({report.marked_for_reprofile} marked for re-profiling)' if report.marked_for_reprofile else ''}, "
            f"facts changed: {report.resource_facts_changed} tables, "
            f"{report.dataset_facts_changed} datasets; search docs written "
            f"{report.docs_upserted} ({report.docs_without_vector} without vectors), "
            f"deleted {report.docs_deleted}"
        )
