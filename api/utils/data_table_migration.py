"""Helpers for ``migrate_data_table_names``: moving old data tables to per-upload names.

Old tables were named from the resource name and dataset title. Postgres cut
those names to 63 bytes, so two resources could end up sharing one table. The
command works out what each ResourceDataTable row needs, then:

  - a short old name (63 bytes or less) can't have collided, so its table is
    renamed in place to "rdt_<row id>";
  - a long old name may already hold another resource's data, so the
    resource is rebuilt from its own stored file (through the normal upload
    flow, with no limit on reading time); the shared table is dropped by the
    delete receiver once its last row has moved. If the file is gone or can't
    become a table, a table only this row uses is renamed and marked
    "unverified" in its comment (listed on every run until the resource is
    re-uploaded); a shared one is left for a manual fix;
  - a row whose table was renamed but not yet pointed at (a crashed run) just
    gets its row updated;
  - a row with no table at all is re-indexed from its file;
  - tables no row uses are listed as orphans, and dropped only from a report
    someone reviewed.

A dry run checks each stored file too, so its report shows what --apply will
do. Each step is safe to rerun; every row's outcome is logged as it happens.
Logs carry ids, outcomes and counts only.
Docs: ./data_indexing_architecture.md
"""

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

import structlog
from django.core.management.base import CommandError
from django.db import connections, transaction
from django.db.utils import OperationalError
from psycopg2 import sql as pg_sql  # type: ignore[import-untyped]

from api.models import AccessModelResource, Resource, ResourceDataTable
from api.utils.data_indexing import index_resource_data
from api.utils.data_table_names import (
    DATA_TABLE_PREFIX,
    MAX_IDENTIFIER_BYTES,
    data_table_name,
    physical_table_name,
)
from api.utils.data_tables import (
    DATA_DB,
    DataDbTable,
    describe_data_table,
    django_table_names,
    drop_data_table,
    error_fields,
    has_indexable_file,
    lock_resource,
    table_built_at,
    table_is_unverified,
)

logger = structlog.get_logger("dataspace.data_table_migration")

# How long a rename waits for readers holding the table before it is skipped.
RENAME_LOCK_TIMEOUT = "2s"
# Per-upload tables younger than this may belong to an upload that hasn't switched yet.
YOUNG_TABLE_AGE = timedelta(hours=1)
LOCK_NOT_AVAILABLE = "55P03"
# Outcomes that leave nothing for a rerun to do (missing or unusable files need a person).
NEEDS_MANUAL_FIX = {
    "missing_file",
    "not_indexable",
    "planned_missing_file",
    "planned_not_indexable",
}
SETTLED_OUTCOMES = NEEDS_MANUAL_FIX | {"already_migrated"}


class DataTableRow(NamedTuple):
    """The fields of a ResourceDataTable row the migration looks at."""

    row_id: Any
    resource_id: Any
    table_name: str
    created: datetime


@dataclass
class MigrationPlan:
    """What each row needs. Rebuilds carry whether another row shares the table."""

    already_migrated: List[DataTableRow] = field(default_factory=list)
    row_updates: List[DataTableRow] = field(default_factory=list)
    renames: List[DataTableRow] = field(default_factory=list)
    rebuilds: List[Tuple[DataTableRow, bool]] = field(default_factory=list)
    missing_tables: List[DataTableRow] = field(default_factory=list)
    orphans: List[DataDbTable] = field(default_factory=list)
    shared_groups: int = 0  # old tables two or more rows point at


def read_data_table_rows() -> List[DataTableRow]:
    """Every ResourceDataTable row, oldest first (one row per tabular resource)."""
    rows = (
        ResourceDataTable.objects.order_by("created")
        .values_list("id", "resource_id", "table_name", "created")
        .iterator()
    )
    return [DataTableRow(*row) for row in rows]


def plan_table_migration(
    rows: List[DataTableRow],
    tables: List[DataDbTable],
    now: datetime,
    resource_id: Optional[str] = None,
) -> MigrationPlan:
    """Sort rows by what they need, given the tables that exist now.

    ``resource_id`` limits the actions to one resource; orphans are always
    worked out against every row.
    """
    existing = {table.name for table in tables}
    rows_per_table = Counter(physical_table_name(row.table_name) for row in rows)
    plan = MigrationPlan(
        orphans=find_orphans(rows, tables, now),
        shared_groups=sum(1 for count in rows_per_table.values() if count > 1),
    )
    for row in rows:
        if resource_id and str(row.resource_id) != str(resource_id):
            continue
        own_name = data_table_name(row.row_id)
        physical = physical_table_name(row.table_name)
        if row.table_name == own_name:
            target = plan.already_migrated if own_name in existing else plan.missing_tables
            target.append(row)
        elif physical in existing and _is_long(row.table_name):
            plan.rebuilds.append((row, rows_per_table[physical] > 1))
        elif physical in existing:
            plan.renames.append(row)
        elif own_name in existing:
            plan.row_updates.append(row)
        else:
            plan.missing_tables.append(row)
    return plan


def _is_long(name: str) -> bool:
    return len(name.encode("utf-8")) > MAX_IDENTIFIER_BYTES


def find_orphans(
    rows: List[DataTableRow], tables: List[DataDbTable], now: datetime
) -> List[DataDbTable]:
    """Tables no row uses, in the order given.

    Never a Django model's table, never a row's (cut) table or its renamed
    "rdt_<row id>" table, and never a per-upload table built less than
    YOUNG_TABLE_AGE ago (its upload may still be switching over).
    """
    in_use = {physical_table_name(row.table_name) for row in rows}
    in_use |= {data_table_name(row.row_id) for row in rows}
    protected = in_use | django_table_names()
    orphans = []
    for table in tables:
        if table.name in protected:
            continue
        built_at = table_built_at(table.comment)
        if (
            table.name.startswith(DATA_TABLE_PREFIX)
            and built_at
            and now - built_at < YOUNG_TABLE_AGE
        ):
            continue
        orphans.append(table)
    return orphans


def point_row_at_its_table(row: DataTableRow) -> str:
    """Finish a rename a crashed run started: point the row at "rdt_<row id>"."""
    try:
        with transaction.atomic():
            lock_resource(Resource.objects.get(pk=row.resource_id))
            updated = ResourceDataTable.objects.filter(
                pk=row.row_id, table_name=row.table_name
            ).update(table_name=data_table_name(row.row_id))
    except Exception as error:
        logger.error("data_table_row_update_failed", row_id=str(row.row_id), **error_fields(error))
        return "failed"
    return "row_updated" if updated else "changed"


def rename_legacy_table(row: DataTableRow, unverified: bool = False) -> str:
    """Rename the row's old table to "rdt_<row id>" and point the row at it.

    ``unverified`` stores the "unverified" mark in the table's comment, for a
    long-named table kept without a rebuild (it may hold another resource's data).

    Holds the resource row, so an upload can't switch it meanwhile; a row an
    upload already replaced is left alone ("changed"). Waits at most
    RENAME_LOCK_TIMEOUT for readers ("skipped_lock"). The data database commits
    first; if the row update then fails, a rerun finds the renamed table and
    updates the row ("row_updated"). Returns "renamed" on success, "failed"
    on any other error (logged).
    """
    new_name = data_table_name(row.row_id)
    try:
        with transaction.atomic():
            resource = Resource.objects.select_related("dataset").get(pk=row.resource_id)
            lock_resource(resource)
            still_legacy = ResourceDataTable.objects.filter(
                pk=row.row_id, table_name=row.table_name
            ).exists()
            if not still_legacy:
                return "changed"
            comment = describe_data_table(resource, built_at=row.created, unverified=unverified)
            _rename_in_data_db(row.table_name, new_name, comment)
            ResourceDataTable.objects.filter(pk=row.row_id).update(table_name=new_name)
    except OperationalError as error:
        if error_fields(error)["error_code"] == LOCK_NOT_AVAILABLE:
            logger.warning("data_table_rename_skipped_lock", row_id=str(row.row_id))
            return "skipped_lock"
        logger.error("data_table_rename_failed", row_id=str(row.row_id), **error_fields(error))
        return "failed"
    except Exception as error:
        logger.error("data_table_rename_failed", row_id=str(row.row_id), **error_fields(error))
        return "failed"
    logger.info("data_table_renamed", row_id=str(row.row_id), table_name=new_name)
    return "renamed"


def _rename_in_data_db(old_name: str, new_name: str, comment: str) -> None:
    with transaction.atomic(using=DATA_DB), connections[DATA_DB].cursor() as cursor:
        cursor.execute(
            pg_sql.SQL("SET LOCAL lock_timeout = {}").format(pg_sql.Literal(RENAME_LOCK_TIMEOUT))
        )
        cursor.execute(
            pg_sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                pg_sql.Identifier(old_name), pg_sql.Identifier(new_name)
            )
        )
        cursor.execute(
            pg_sql.SQL("COMMENT ON TABLE {} IS {}").format(
                pg_sql.Identifier(new_name), pg_sql.Literal(comment)
            )
        )


def file_problem(resource: Resource) -> Optional[str]:
    """Why the resource's stored file can't become a table, or None if it can.

    "missing_file" (no file, or gone from storage) or "not_indexable" (a format
    that never gets a table, e.g. the file was later replaced by a PDF).
    Storage errors are raised.
    """
    details = getattr(resource, "resourcefiledetails", None)
    if not details or not details.file:
        return "missing_file"
    if not has_indexable_file(resource):
        return "not_indexable"
    if not details.file.storage.exists(details.file.name):
        return "missing_file"
    return None


def rebuild_decision(row: DataTableRow, shared: bool) -> str:
    """What --apply will do with a long-named old table.

    "rebuild" when the stored file can become a table; otherwise
    "unverified_rename" for a table only this row uses, or the file problem
    ("missing_file" / "not_indexable") for a shared one, which is left alone.
    "check_failed" (logged) when the check itself fails.
    """
    try:
        problem = file_problem(Resource.objects.get(pk=row.resource_id))
    except Exception as error:
        logger.error("data_table_file_check_failed", row_id=str(row.row_id), **error_fields(error))
        return "check_failed"
    if problem is None:
        return "rebuild"
    return problem if shared else "unverified_rename"


def reindex_decision(row: DataTableRow) -> str:
    """What --apply will do with a row whose table is gone: "reindex" or the file problem."""
    try:
        problem = file_problem(Resource.objects.get(pk=row.resource_id))
    except Exception as error:
        logger.error("data_table_file_check_failed", row_id=str(row.row_id), **error_fields(error))
        return "check_failed"
    return problem or "reindex"


def rebuild_from_file(row: DataTableRow, shared: bool) -> str:
    """Carry out the rebuild decision for a long-named old table.

    Rebuilds go through the normal upload flow with no limit on reading time,
    so the resource gets a fresh per-upload table and the old one is dropped
    once no row uses it. Returns "rebuilt", "unverified" (renamed and marked),
    the rename's other outcomes, a file problem, "check_failed" or "failed".
    """
    decision = rebuild_decision(row, shared)
    if decision == "unverified_rename":
        outcome = rename_legacy_table(row, unverified=True)
        return "unverified" if outcome == "renamed" else outcome
    if decision != "rebuild":
        return decision
    return _index_without_time_limit(row)


def reindex_missing_table(row: DataTableRow) -> str:
    """Re-index a row whose table is gone: "reindexed", a file problem, or a failure."""
    decision = reindex_decision(row)
    if decision != "reindex":
        return decision
    outcome = _index_without_time_limit(row)
    return "reindexed" if outcome == "rebuilt" else outcome


def _index_without_time_limit(row: DataTableRow) -> str:
    try:
        resource = Resource.objects.select_related("dataset").get(pk=row.resource_id)
        return "rebuilt" if index_resource_data(resource, load_timeout=None) else "failed"
    except Exception as error:
        logger.error("data_table_rebuild_failed", row_id=str(row.row_id), **error_fields(error))
        return "failed"


def find_unverified(rows: List[DataTableRow], tables: List[DataDbTable]) -> List[DataTableRow]:
    """Rows whose table carries the "unverified" mark — kept without a rebuild, needing a check."""
    marked = {table.name for table in tables if table_is_unverified(table.comment)}
    return [
        row
        for row in rows
        if physical_table_name(row.table_name) in marked or data_table_name(row.row_id) in marked
    ]


def access_models_touched(resource_ids: Iterable[Any]) -> List[str]:
    """Access models whose column choices a rebuild resets (columns are recreated)."""
    ids = (
        AccessModelResource.objects.filter(resource_id__in=list(resource_ids))
        .values_list("access_model_id", flat=True)
        .distinct()
    )
    return sorted(str(access_model_id) for access_model_id in ids)


def read_reviewed_orphans(path: str) -> Set[str]:
    """The orphan table names listed in a report someone reviewed.

    Raises CommandError if the file can't be read or isn't a report, so a bad
    path stops the run before it changes anything.
    """
    try:
        with open(path, encoding="utf-8") as report:
            return {orphan["name"] for orphan in json.load(report)["orphans"]}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CommandError(f"Can't read the reviewed report {path}: {error}") from error


def same_file(first: str, second: str) -> bool:
    """Whether two paths name the same file."""
    return os.path.abspath(first) == os.path.abspath(second)


def drop_reviewed_orphans(reviewed: Set[str], current_orphans: List[DataDbTable]) -> List[str]:
    """Drop tables that are both in the reviewed report and still orphans now."""
    dropped = []
    for table in current_orphans:
        if table.name in reviewed and drop_data_table(table.name):
            dropped.append(table.name)
    return dropped


def write_report(path: str, report: Dict[str, Any]) -> None:
    """Write the run's report as JSON (ids, names, outcomes and sizes; no data)."""
    with open(path, "w", encoding="utf-8") as out:
        json.dump(report, out, indent=2, default=str)


def record_outcome(
    row: DataTableRow, action: str, outcome: str, shared: Optional[bool] = None
) -> Dict[str, Any]:
    """Log one row's outcome as it happens, and return its line for the report."""
    entry: Dict[str, Any] = {
        "row_id": str(row.row_id),
        "resource_id": str(row.resource_id),
        "table_name": row.table_name,
        "action": action,
        "outcome": outcome,
    }
    if shared is not None:
        entry["shared"] = shared
    logger.info(
        "data_table_migration_row",
        row_id=entry["row_id"],
        resource_id=entry["resource_id"],
        action=action,
        outcome=outcome,
    )
    return entry


def nothing_left_to_do(entries: List[Dict[str, Any]]) -> bool:
    """Whether a rerun would change nothing: every row is migrated or needs a person."""
    return all(entry["outcome"] in SETTLED_OUTCOMES for entry in entries)


def build_report(
    mode: str,
    generated_at: datetime,
    entries: Optional[List[Dict[str, Any]]] = None,
    orphans: Optional[List[DataDbTable]] = None,
    orphans_dropped: Optional[List[str]] = None,
    access_models: Optional[List[str]] = None,
    unverified: Optional[List[DataTableRow]] = None,
    shared_groups: int = 0,
    status: str = "complete",
) -> Dict[str, Any]:
    """The run's JSON report: counts by outcome, per-row lines, orphans, unverified tables.

    Orphans carry their size and comment (resource, dataset, build time) so a
    reviewer can tell what each is before approving its drop.
    """
    entries = entries or []
    counts = Counter(entry["outcome"] for entry in entries)
    return {
        "mode": mode,
        "status": status,
        "generated_at": generated_at.isoformat(),
        "counts": dict(sorted(counts.items())),
        "shared_groups": shared_groups,
        "rows": entries,
        "needs_manual_fix": [e for e in entries if e["outcome"] in NEEDS_MANUAL_FIX],
        "unverified_tables": [
            {"row_id": str(r.row_id), "resource_id": str(r.resource_id), "table_name": r.table_name}
            for r in unverified or []
        ],
        "orphans": [
            {"name": t.name, "size_bytes": t.size_bytes, "comment": t.comment}
            for t in orphans or []
        ],
        "orphans_dropped": orphans_dropped or [],
        "access_models_touched": access_models or [],
    }


def summary_lines(report: Dict[str, Any], report_path: str) -> List[str]:
    """A short plain-text summary of a report, for the terminal and the logs."""
    orphan_bytes = sum(orphan["size_bytes"] for orphan in report["orphans"])
    lines = [f"{report['mode']}: report written to {report_path}"]
    lines += [f"  {outcome}: {count}" for outcome, count in report["counts"].items()]
    lines.append(f"  old tables shared by several rows: {report['shared_groups']}")
    lines.append(
        f"  rows needing a manual fix (file missing or unusable): {len(report['needs_manual_fix'])}"
    )
    lines.append(
        f"  unverified tables (may hold another resource's data): {len(report['unverified_tables'])}"
    )
    lines.append(f"  orphans listed: {len(report['orphans'])} ({orphan_bytes} bytes)")
    lines.append(f"  orphans dropped: {len(report['orphans_dropped'])}")
    lines.append(
        f"  access models with column choices reset: {len(report['access_models_touched'])}"
    )
    logger.info(
        "data_table_migration_finished",
        mode=report["mode"],
        shared_groups=report["shared_groups"],
        needs_manual_fix=len(report["needs_manual_fix"]),
        unverified_tables=len(report["unverified_tables"]),
        orphans_listed=len(report["orphans"]),
        orphans_dropped=len(report["orphans_dropped"]),
        **report["counts"],
    )
    return lines
