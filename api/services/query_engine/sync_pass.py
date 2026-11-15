"""FLOW: one ``qe_sync`` pass — make profiles and facts match what the database says.

A level-triggered pass, run every couple of minutes by ``qe_sync --loop``. It
compares what the processing set (platform scope plus enabled collaboratives)
should have with what is profiled, and fixes the difference, so a missed
signal, a bulk update, a crash or downtime heals on the next pass. Safety
never depends on it: every endpoint re-checks corpus and scope itself.

1. Close stale database connections; take the pass lock (skip when held).
3. Load the processing set in chunks, with everything prefetched.
4. Profile the tables whose stats are missing or out of date, within the
   pass's limits (tables per pass, a time budget that starts once the lock is
   held and is shared down to each table, failure back-off).
5. Recompute facts for every table and dataset; store hashes that changed.

(Steps 2 and 6–8, the AI-search index, arrive with search.)

Docs: api/views/query_engine/architecture.md
"""

import time
from typing import Optional
from uuid import UUID

import structlog
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from api.services.query_engine.corpus import load_corpus
from api.services.query_engine.geography_match import load_geography_index
from api.services.query_engine.sync_lock import sync_lock
from api.services.query_engine.sync_steps import (
    PassBudget,
    SyncReport,
    find_stale_profiles,
    mark_for_reprofile,
    profile_one,
    refresh_facts,
)

logger = structlog.get_logger("dataspace.query_engine.sync")


def run_sync_pass(
    *,
    reprofile: bool = False,
    only_resource_id: Optional[UUID] = None,
    lock_wait_seconds: float = 0,
) -> SyncReport:
    """Run one pass; returns what it did (``skipped`` when another pass holds the lock).

    ``reprofile`` first marks every READY profile as due; this pass and the
    next ones then re-profile them within their usual limits.
    """
    started = time.monotonic()

    # A long-running process can hold connections the database already dropped.
    close_old_connections()

    # Only one pass at a time, across every process and container.
    with sync_lock(wait_seconds=lock_wait_seconds) as held:
        if not held:
            logger.info("qe_sync_skipped_lock_held")
            return SyncReport(skipped=True)

        report = SyncReport()
        # The time budget starts once the lock is held: waiting for it doesn't count.
        budget = PassBudget(
            profiles_left=settings.QE_PROFILES_PER_PASS,
            deadline=time.monotonic() + settings.QE_SYNC_MAX_SECONDS,
        )
        now = timezone.now()

        # On request, mark every profile as due, so this and later passes redo them all.
        if reprofile:
            report.marked_for_reprofile = mark_for_reprofile(now)

        # Known state and district names, read once for every table this pass profiles.
        geography = load_geography_index()

        # Walk the processing set a chunk at a time.
        for chunk in load_corpus():
            report.datasets += len(chunk)

            # Profile tables whose stats are missing or stale, while the pass has budget left.
            for resource in find_stale_profiles(chunk, now, only_resource_id):
                if not budget.can_profile():
                    break
                budget.spend_profile()
                report.count_profile(
                    profile_one(resource, geography, budget.seconds_left())
                )

            # Recompute facts for every table and dataset; store the hashes that changed.
            changed = refresh_facts(chunk)
            report.resource_facts_changed += changed["resources"]
            report.dataset_facts_changed += changed["datasets"]

        logger.info(
            "qe_sync_pass_done",
            duration_ms=int((time.monotonic() - started) * 1000),
            **report.__dict__,
        )
        return report
