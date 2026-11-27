"""FLOW: one ``qe_sync`` pass — make profiles and facts match what the database says.

A level-triggered pass, run every couple of minutes by ``qe_sync --loop``. It
compares what the processing set (platform scope plus enabled collaboratives)
should have with what is profiled, and fixes the difference, so a missed
signal, a bulk update, a crash or downtime heals on the next pass. Safety
never depends on it: every endpoint re-checks corpus and scope itself.

1. Close stale database connections; take the pass lock (skip when held).
2. Make sure the AI-search index exists (Elasticsearch down, or a changed
   vector size → the search steps 6–8 are skipped this pass, logged once).
3. Load the processing set in chunks, with everything prefetched.
4. Profile the tables whose stats are missing or out of date, within the
   pass's limits (tables per pass, a time budget that starts once the lock is
   held and is shared down to each table, failure back-off).
5. Recompute facts for every table and dataset; store hashes that changed.
6. Build each chunk's search cards and compare them with the index.
7. Delete documents that are no longer in the processing set.
8. Write new and changed documents (at most QE_DOCS_PER_PASS), with vectors
   when the embeddings service answers, without them otherwise.

``run_index_rebuild`` (``qe_sync --rebuild-index``) writes every card into a
new index version and only then moves the alias; the old index serves search
throughout, and a failed rebuild leaves it in place.

Docs: api/views/query_engine/architecture.md
"""

import time
from typing import Optional
from uuid import UUID

import structlog
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from api.services.query_engine.corpus import load_corpus, sector_slugs_with_parents
from api.services.query_engine.embeddings import embeddings_configured
from api.services.query_engine.geography_match import load_geography_index
from api.services.query_engine.sync_lock import sync_lock
from api.services.query_engine.sync_steps import (
    IndexPlan,
    PassBudget,
    SyncReport,
    apply_index_plan,
    chunk_cards,
    find_stale_profiles,
    mark_for_reprofile,
    open_search_index,
    plan_index_changes,
    profile_one,
    read_index_states,
    refresh_facts,
    write_cards,
)
from search.query_engine.index import create_next_index, delete_index, swap_alias

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

        # Make sure the search index exists; without it the search steps are skipped.
        index = open_search_index()

        # What the index holds now: each document's card hash and whether it has a vector.
        states = read_index_states(index) if index else None
        report.index_ready = states is not None
        plan = IndexPlan(cap=settings.QE_DOCS_PER_PASS)

        # Known state and district names, and sector slugs, read once for the whole pass.
        geography = load_geography_index()
        sector_slugs = sector_slugs_with_parents()

        # Walk the processing set a chunk at a time.
        for chunk in load_corpus():
            report.datasets += len(chunk)

            # Profile tables whose stats are missing or stale, while the pass has budget left.
            for resource in find_stale_profiles(chunk, now, only_resource_id):
                if not budget.can_profile():
                    break
                budget.spend_profile()
                report.count_profile(profile_one(resource, geography, budget.seconds_left()))

            # Recompute facts for every table and dataset; store the hashes that changed.
            changed = refresh_facts(chunk)
            report.resource_facts_changed += changed["resources"]
            report.dataset_facts_changed += changed["datasets"]

            # Build this chunk's search cards and note which ones the index needs.
            if states is not None:
                plan_index_changes(
                    plan, chunk_cards(chunk, sector_slugs), states, embeddings_configured()
                )

        # Remove documents no longer in the processing set, then write new and changed ones.
        if index is not None and states is not None:
            written = apply_index_plan(index, plan, states)
            report.docs_deleted = written["deleted"]
            report.docs_upserted = written["upserted"]
            report.docs_without_vector = written["without_vector"]

        logger.info(
            "qe_sync_pass_done",
            duration_ms=int((time.monotonic() - started) * 1000),
            **report.__dict__,
        )
        return report


class RebuildIncomplete(Exception):
    """The new index could not be filled the way search needs (e.g. embeddings were down)."""


def run_index_rebuild(*, lock_wait_seconds: float = 0) -> SyncReport:
    """Write every card into a new index version, then move the alias to it.

    Under the pass lock. The old index keeps serving search until the alias
    moves; if anything fails — including documents left without a vector
    while an embeddings service is configured — the new index is deleted and
    the alias is left alone.
    """
    started = time.monotonic()

    # A long-running process can hold connections the database already dropped.
    close_old_connections()

    # Only one pass or rebuild at a time.
    with sync_lock(wait_seconds=lock_wait_seconds) as held:
        if not held:
            logger.info("qe_sync_skipped_lock_held")
            return SyncReport(skipped=True)

        report = SyncReport()

        # A fresh, empty index version beside the live one.
        new_index, old_index = create_next_index(int(settings.QE_EMBEDDINGS_DIMS))
        try:
            # Sector slugs, read once for every card.
            sector_slugs = sector_slugs_with_parents()

            # Fill it completely, chunk by chunk.
            for chunk in load_corpus():
                report.datasets += len(chunk)
                written, without_vector = write_cards(new_index, chunk_cards(chunk, sector_slugs))
                report.docs_upserted += written
                report.docs_without_vector += without_vector

            # With an embeddings service configured, an index without vectors is not a rebuild.
            if embeddings_configured() and report.docs_without_vector:
                raise RebuildIncomplete(f"{report.docs_without_vector} documents got no vector")

            # Move the alias in one step, so search switches over at once.
            swap_alias(new_index, old_index)
        except Exception:
            # A failed rebuild leaves the live index serving; drop the half-written one.
            delete_index(new_index)
            logger.error("qe_sync_rebuild_failed", index=new_index)
            raise

        # The old version is no longer used.
        if old_index:
            delete_index(old_index)
        logger.info(
            "qe_sync_rebuild_done",
            index=new_index,
            duration_ms=int((time.monotonic() - started) * 1000),
            docs=report.docs_upserted,
        )
        return report
