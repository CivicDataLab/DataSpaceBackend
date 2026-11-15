"""Building a table's profile stats from its data table, and saving profiles safely.

- ``build_resource_stats`` reads one analysable resource's data table
  (read-only, time-limited statements) and returns its stats: row count,
  layout, and per column its storage type, kind, counts, min / max / mean,
  common values, examples, role, place match, time values, total-row labels
  and odd tokens. Columns are listed from ResourceSchema (full headers, in
  file order) and matched to the table by the 63-byte cut; a header with no
  match is listed as unavailable; columns after the first 300 are listed by
  name only (``not_profiled``). Columns that time out, or that the table's
  time budget doesn't reach, leave the profile incomplete, not failed; an
  incomplete profile is tried again after 6 hours.
- ``save_resource_profile_if_current`` stores READY stats only if the
  resource still points at the data table they were computed from (checked
  under the resource's row lock, the same lock an upload's switch takes).
- ``record_profile_failure`` stores an error code with a back-off of 2ⁿ minutes
  (at most 24 h), reset when the data table changes.
- ``write_resource_facts_hash`` / ``write_dataset_facts_hash`` store a new
  facts hash with one conditional UPDATE on the previous hash, and mark the
  summary as needed.
- ``dataset_rollup`` builds a dataset's facts from its table profiles on read.

Docs: api/views/query_engine/architecture.md
"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch, prefetch_related_objects
from django.utils import timezone

from api.models import (
    Dataset,
    DatasetProfile,
    Resource,
    ResourceDataTable,
    ResourceProfile,
    ResourceSchema,
)
from api.models.ResourceProfile import ResourceProfileStatus
from api.services.query_engine.column_roles import (
    KIND_NUMERIC_TEXT,
    KIND_TEXT,
    detect_kind,
    detect_layout,
    detect_role,
    detect_time,
    not_analysable_reasons,
    total_markers_in,
)
from api.services.query_engine.column_stats import (
    ColumnRef,
    count_rows,
    odd_tokens_from_values,
    read_column_stats,
)
from api.services.query_engine.data_reader import read_table_columns
from api.services.query_engine.errors import NotAnalysable, ProfileNotReady
from api.services.query_engine.facts import dataset_facts
from api.services.query_engine.geography_match import GeographyIndex, match_places
from api.services.query_engine.physical_names import physical_column_name
from api.utils.data_tables import lock_resource

PROFILER_VERSION = 1
MAX_PROFILED_COLUMNS = 300
TOP_VALUES = 10
TOP_VALUES_MAX_DISTINCT = 50
EXAMPLES = 3
MAX_BACKOFF_MINUTES = 24 * 60
INCOMPLETE_RETRY_HOURS = 6


def build_resource_stats(
    resource: Resource, geography: GeographyIndex, time_budget_seconds: Optional[float] = None
) -> Dict[str, Any]:
    """The stats of a resource's current data table (see the module comment for the shape).

    Columns not reached within ``time_budget_seconds`` (default QE_SYNC_MAX_SECONDS)
    are left without stats and the profile is marked incomplete.
    """
    budget = settings.QE_SYNC_MAX_SECONDS if time_budget_seconds is None else time_budget_seconds
    deadline = time.monotonic() + budget
    table = resource.resourcedatatable.table_name
    physical = read_table_columns(table)
    schema_rows = sorted(resource.resourceschema_set.all(), key=lambda row: row.id)
    headers = [row.field_name for row in schema_rows] or list(physical)

    columns: List[Dict[str, Any]] = []
    to_profile: List[ColumnRef] = []
    for header in headers:
        storage_type = physical.get(physical_column_name(header))
        if storage_type is None:
            columns.append({"name": header, "available": False, "profiled": False})
        elif len(to_profile) >= MAX_PROFILED_COLUMNS:
            columns.append(
                {"name": header, "available": True, "profiled": False, "storage_type": storage_type}
            )
        else:
            to_profile.append(ColumnRef(header, storage_type))
            columns.append({"name": header})

    row_count = count_rows(table)
    raw, unavailable = read_column_stats(
        table, to_profile, deadline=deadline, resource_id=str(resource.id)
    )
    described = {
        ref.header: _describe_column(ref, raw.get(ref.header), row_count, geography)
        for ref in to_profile
    }
    columns = [described.get(column["name"], column) for column in columns]

    layout, year_columns = detect_layout([c for c in columns if c.get("profiled")])
    return {
        "row_count": row_count,
        "layout": layout,
        "year_columns": year_columns,
        "columns": columns,
        "stats_complete": not unavailable,
        "notes": _notes(columns, unavailable),
        "analysable": not not_analysable_reasons(row_count, columns),
        "not_analysable_reasons": not_analysable_reasons(row_count, columns),
    }


def _describe_column(
    ref: ColumnRef, raw: Optional[Dict[str, Any]], row_count: int, geography: GeographyIndex
) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "name": ref.header,
        "storage_type": ref.storage_type,
        "available": True,
        "profiled": True,
    }
    if raw is None:
        kind = detect_kind(ref.storage_type, 0, 0, 0)
        return {
            **base,
            "stats_unavailable": True,
            "kind": kind,
            "role": detect_role(ref.header, kind, None, None),
        }

    kind = raw["kind"]
    value_rows = raw.get("values")
    values = [str(value) for value, _ in value_rows or []]
    geo = match_places(ref.header, values, geography) if kind == KIND_TEXT and values else None
    time = detect_time(ref.header, kind, values or None)
    examples = values[:EXAMPLES] if values else [str(v) for v in raw.get("samples", [])][:EXAMPLES]
    non_null = int(raw.get("non_null") or 0)
    distinct = int(raw.get("distinct") or 0)
    column = {
        **base,
        "kind": kind,
        "non_null": non_null,
        "null_pct": round(100.0 * (row_count - non_null) / row_count, 1) if row_count else 0.0,
        "distinct": distinct,
        "placeholder_count": int(raw.get("placeholder_count") or 0),
        "min": raw.get("min"),
        "max": raw.get("max"),
        "mean": raw.get("mean"),
        "non_finite": bool(raw.get("non_finite")),
        "top_values": (
            [[value, hits] for value, hits in value_rows[:TOP_VALUES]]
            if value_rows and distinct <= TOP_VALUES_MAX_DISTINCT
            else None
        ),
        "examples": examples,
        "geo": geo,
        "time": time,
        "total_markers": total_markers_in(values),
        "non_numeric_tokens": (
            (odd_tokens_from_values(value_rows) if value_rows else _token_list(raw))
            if kind == KIND_NUMERIC_TEXT
            else []
        ),
    }
    column["role"] = detect_role(ref.header, kind, geo, time)
    return column


def _token_list(raw: Dict[str, Any]) -> List[str]:
    return [str(value) for value, _ in raw.get("odd_tokens", [])]


def _notes(columns: List[Dict[str, Any]], unavailable: List[str]) -> List[str]:
    notes: List[str] = []
    not_profiled = sum(1 for c in columns if c.get("available") and not c.get("profiled"))
    if not_profiled:
        notes.append(f"{not_profiled} columns after the first {MAX_PROFILED_COLUMNS} not profiled")
    missing = sum(1 for c in columns if c.get("available") is False)
    if missing:
        notes.append(f"{missing} columns listed in the schema are not in the data table")
    if unavailable:
        notes.append(f"stats unavailable for {len(unavailable)} columns (the read took too long)")
    non_finite = [c["name"] for c in columns if c.get("non_finite")]
    if non_finite:
        notes.append(
            f"infinite or undefined values left out of min/max/mean in {len(non_finite)} columns"
        )
    return notes


def current_data_table_id(resource_id: UUID) -> Optional[UUID]:
    """The id of the resource's current ResourceDataTable row (None when it has none)."""
    return (
        ResourceDataTable.objects.filter(resource_id=resource_id)
        .values_list("id", flat=True)
        .first()
    )


def save_resource_profile_if_current(
    resource: Resource, data_table_id: UUID, stats: Dict[str, Any]
) -> bool:
    """Store READY stats for the resource, unless its data table moved since they were computed.

    Returns whether it stored them. Keeps the facts hash and summary fields as they were.
    """
    with transaction.atomic():
        lock_resource(resource)
        if current_data_table_id(resource.pk) != data_table_id:
            return False
        ResourceProfile.objects.update_or_create(
            resource_id=resource.pk,
            defaults={
                "data_table_id": data_table_id,
                "profiler_version": PROFILER_VERSION,
                "status": ResourceProfileStatus.READY,
                "error": None,
                "failed_attempts": 0,
                # An incomplete profile (some columns timed out) is tried again later.
                "retry_after": (
                    None
                    if stats.get("stats_complete", True)
                    else timezone.now() + timedelta(hours=INCOMPLETE_RETRY_HOURS)
                ),
                "stats": stats,
            },
        )
    return True


def record_profile_failure(
    resource: Resource, data_table_id: UUID, error_code: str, now: Optional[datetime] = None
) -> ResourceProfile:
    """Store a failed profile attempt with its error code and back-off; a new data table resets it."""
    now = now or timezone.now()
    previous = ResourceProfile.objects.filter(resource_id=resource.pk).first()
    same_table = previous is not None and previous.data_table_id == data_table_id
    attempts = previous.failed_attempts + 1 if previous is not None and same_table else 1
    defaults: Dict[str, Any] = {
        "data_table_id": data_table_id,
        "profiler_version": PROFILER_VERSION,
        "status": ResourceProfileStatus.FAILED,
        "error": error_code[:64],
        "failed_attempts": attempts,
        "retry_after": now + timedelta(minutes=min(2**attempts, MAX_BACKOFF_MINUTES)),
    }
    if not same_table:
        defaults["stats"] = None
    profile, _ = ResourceProfile.objects.update_or_create(
        resource_id=resource.pk, defaults=defaults
    )
    return profile


def write_resource_facts_hash(profile: ResourceProfile, new_hash: str) -> bool:
    """Store a changed facts hash (summary needed, rejections reset) if no one changed it first."""
    written = _write_facts_hash(ResourceProfile, profile.pk, profile.facts_hash, new_hash)
    if written:
        profile.facts_hash = new_hash
    return written


def write_dataset_facts_hash(dataset: Dataset, new_hash: str) -> bool:
    """The same for a dataset, creating its profile row the first time.

    Uses the dataset's already-loaded profile when there is one (no extra query).
    """
    profile = getattr(dataset, "qe_profile", None)
    if profile is None:
        profile, _ = DatasetProfile.objects.get_or_create(dataset_id=dataset.pk)
    written = _write_facts_hash(DatasetProfile, profile.pk, profile.facts_hash, new_hash)
    if written:
        profile.facts_hash = new_hash
    return written


def _write_facts_hash(model: Any, pk: UUID, old_hash: str, new_hash: str) -> bool:
    if old_hash == new_hash:
        return False
    updated = model.objects.filter(pk=pk, facts_hash=old_hash).update(
        facts_hash=new_hash, summary_needed=True, summary_rejections=0, modified=timezone.now()
    )
    return bool(updated)


def ready_stats(resource: Resource) -> Optional[Dict[str, Any]]:
    """The resource's stats when its profile is READY for its current data table, else None."""
    profile = getattr(resource, "qe_profile", None)
    data_table = getattr(resource, "resourcedatatable", None)
    if (
        profile is None
        or data_table is None
        or profile.status != ResourceProfileStatus.READY
        or profile.data_table_id != data_table.id
        or profile.stats is None
    ):
        return None
    return dict(profile.stats)


def dataset_tables(dataset: Dataset) -> List[Tuple[Resource, Optional[Dict[str, Any]]]]:
    """The dataset's active tables (resources with a data table), each with its READY stats.

    Stats are None while a table is not yet profiled. The caller has checked the
    dataset is in the corpus. No queries when the resources, their data tables
    and profiles were prefetched (the sync pass); otherwise one per relation.
    """
    return [
        (resource, ready_stats(resource))
        for resource in dataset.resources.all()
        if resource.is_active and getattr(resource, "resourcedatatable", None) is not None
    ]


def dataset_rollup(dataset: Dataset) -> Dict[str, Any]:
    """A dataset's facts, built now from its tables' profiles and its metadata."""
    return dataset_facts(dataset, dataset_tables(dataset))


def require_ready_profile(resource: Resource) -> ResourceProfile:
    """The resource's profile when READY for its current data table; else ProfileNotReady (409)."""
    if ready_stats(resource) is None:
        raise ProfileNotReady(reason="profile_not_ready", resource_id=str(resource.id))
    return resource.qe_profile


def load_dataset_tables(dataset: Dataset) -> List[Tuple[Resource, Optional[Dict[str, Any]]]]:
    """Prefetch the dataset's resources and metadata in a fixed number of queries; its tables."""
    resources = Resource.objects.select_related(
        "resourcedatatable", "resourcefiledetails", "qe_profile"
    ).prefetch_related(
        Prefetch("resourceschema_set", queryset=ResourceSchema.objects.order_by("id"))
    )
    prefetch_related_objects(
        [dataset], Prefetch("resources", queryset=resources), "tags", "sectors", "geographies"
    )
    return dataset_tables(dataset)


def require_analysable(stats: Dict[str, Any], resource: Resource) -> None:
    """Raise NotAnalysable (422, with the reasons) for a table with no rows or no numbers."""
    reasons = stats.get("not_analysable_reasons") or []
    if not stats.get("analysable"):
        raise NotAnalysable(
            details={"reasons": reasons or ["no_numeric_measure"]},
            reason="not_analysable",
            resource_id=str(resource.id),
        )
