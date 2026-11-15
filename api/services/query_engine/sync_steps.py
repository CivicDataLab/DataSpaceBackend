"""The steps of one ``qe_sync`` pass (the flow is ./sync_pass.py).

- ``PassBudget``: how many tables this pass may still profile, and until when.
- ``find_stale_profiles``: the active tables of a chunk whose stats are missing
  or out of date — no profile yet, a new data table since (a re-upload), an
  older ``PROFILER_VERSION``, or an incomplete profile whose retry time has
  come — leaving out failed ones still in their back-off.
  ``only_resource_id`` narrows to one table (forced).
- ``mark_for_reprofile``: mark every READY profile as due (``--reprofile``,
  after the Geography list is reloaded); passes then work through them.
- ``profile_one``: compute one table's stats and save them if its data table
  hasn't moved meanwhile; a failure is stored as an error code with back-off
  and never stops the other tables.
- ``refresh_facts``: recompute the facts of every table (with READY stats) and
  dataset in a chunk and store the hashes that changed. Run every pass, so
  metadata edits (descriptions, titles, tags, an organisation renamed by a
  bulk update) are picked up without any signal.

Logs carry ids, counts and error codes only.

Docs: api/views/query_engine/architecture.md
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

import structlog

from api.models import Dataset, Resource, ResourceProfile
from api.models.ResourceProfile import ResourceProfileStatus
from api.services.query_engine.errors import QueryEngineError
from api.services.query_engine.corpus import processing_set_q
from api.services.query_engine.facts import dataset_facts, facts_hash, resource_facts
from api.services.query_engine.geography_match import GeographyIndex
from api.services.query_engine.profiles import (
    PROFILER_VERSION,
    build_resource_stats,
    dataset_tables,
    record_profile_failure,
    save_resource_profile_if_current,
    write_dataset_facts_hash,
    write_resource_facts_hash,
)
from api.utils.data_tables import error_fields

logger = structlog.get_logger("dataspace.query_engine.sync")

PROFILED = "profiled"
TABLE_MOVED = "table_moved"
FAILED = "failed"


@dataclass
class PassBudget:
    """What one pass may still spend: tables to profile and wall-clock time."""

    profiles_left: int
    deadline: float

    def can_profile(self) -> bool:
        return self.profiles_left > 0 and time.monotonic() < self.deadline

    def seconds_left(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def spend_profile(self) -> None:
        self.profiles_left -= 1


@dataclass
class SyncReport:
    """What a pass did, by count (logged at the end of every pass)."""

    skipped: bool = False
    datasets: int = 0
    marked_for_reprofile: int = 0
    profiles: Dict[str, int] = field(default_factory=dict)
    resource_facts_changed: int = 0
    dataset_facts_changed: int = 0
    index_ready: bool = False
    docs_deleted: int = 0
    docs_upserted: int = 0
    docs_without_vector: int = 0

    def count_profile(self, outcome: str) -> None:
        self.profiles[outcome] = self.profiles.get(outcome, 0) + 1


def _has_table(resource: Resource) -> bool:
    return (
        resource.is_active and getattr(resource, "resourcedatatable", None) is not None
    )


def _is_stale(resource: Resource, now: datetime) -> bool:
    profile: Optional[ResourceProfile] = getattr(resource, "qe_profile", None)
    if profile is None:
        return True
    if profile.data_table_id != resource.resourcedatatable.id:
        return True
    # A retry time (a failure's back-off, an incomplete profile, a re-profile request) decides.
    if profile.retry_after is not None:
        return profile.retry_after <= now
    if profile.status == ResourceProfileStatus.FAILED:
        return True
    return profile.profiler_version != PROFILER_VERSION


def find_stale_profiles(
    datasets: List[Dataset], now: datetime, only_resource_id: Optional[UUID] = None
) -> List[Resource]:
    """The chunk's active tables that need (re)profiling, in dataset and name order."""
    stale: List[Resource] = []
    for dataset in datasets:
        for resource in dataset.resources.all():
            if not _has_table(resource):
                continue
            if only_resource_id is not None:
                if resource.id == only_resource_id:
                    stale.append(resource)
            elif _is_stale(resource, now):
                stale.append(resource)
    return stale


def mark_for_reprofile(now: datetime) -> int:
    """Mark every READY profile in the processing set as due now; returns how many.

    Stored on the profiles (as a retry time), so passes work through all of
    them under their usual limits, however many passes that takes.
    """
    return ResourceProfile.objects.filter(
        status=ResourceProfileStatus.READY,
        resource__dataset__in=Dataset.objects.filter(processing_set_q()),
    ).update(retry_after=now)


def profile_one(
    resource: Resource,
    geography: GeographyIndex,
    time_budget_seconds: Optional[float] = None,
) -> str:
    """Profile one table and save it if still current.

    Returns "profiled", "table_moved" or "failed:<error code>". After a save,
    the table's facts hash is written straight away, so a summary written for
    the old data stops showing at once.
    """
    data_table_id = resource.resourcedatatable.id
    try:
        stats = build_resource_stats(resource, geography, time_budget_seconds)
    except QueryEngineError as error:
        _store_failure(resource, data_table_id, error.code)
        logger.warning(
            "qe_profile_failed", resource_id=str(resource.id), code=error.code
        )
        return f"{FAILED}:{error.code}"
    except Exception as error:
        _store_failure(resource, data_table_id, "profile_failed")
        logger.error(
            "qe_profile_failed", resource_id=str(resource.id), **error_fields(error)
        )
        return f"{FAILED}:profile_failed"
    if not save_resource_profile_if_current(resource, data_table_id, stats):
        logger.info("qe_profile_table_moved", resource_id=str(resource.id))
        return TABLE_MOVED
    resource.qe_profile = ResourceProfile.objects.get(resource_id=resource.pk)
    write_resource_facts_hash(
        resource.qe_profile, facts_hash(resource_facts(resource, stats))
    )
    return PROFILED


def _store_failure(resource: Resource, data_table_id: UUID, code: str) -> None:
    resource.qe_profile = record_profile_failure(resource, data_table_id, code)


def refresh_facts(datasets: List[Dataset]) -> Dict[str, int]:
    """Recompute and store changed facts hashes for a chunk: ``{"resources": n, "datasets": n}``."""
    changed = {"resources": 0, "datasets": 0}
    for dataset in datasets:
        tables = dataset_tables(dataset)
        for resource, stats in tables:
            if stats is None:
                continue
            new_hash = facts_hash(resource_facts(resource, stats))
            if write_resource_facts_hash(resource.qe_profile, new_hash):
                changed["resources"] += 1
        if write_dataset_facts_hash(
            dataset, facts_hash(dataset_facts(dataset, tables))
        ):
            changed["datasets"] += 1
    return changed
