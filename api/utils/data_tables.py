"""Helpers for copying uploaded files into tables in the data database.

The upload flow (``index_resource_data`` in ./data_indexing.py) reads a
resource's file, builds a brand-new table for it, then switches the resource's
ResourceDataTable row over to that table in one main-database commit. Old tables
are dropped after the commit by the row's delete receiver
(api/signals/data_table_signals.py). Each helper here does one step of that.

Tables live in the separate ``data_db`` database (its statements autocommit);
the rows that point at them (ResourceDataTable, ResourceSchema) live in the
main database. New SQL composes names and comments with psycopg2's
``sql.Identifier`` / ``sql.Literal``, never with string formatting.

Logs carry ids, counts and error codes only — never file contents or values.
Docs: ./data_indexing_architecture.md
"""

import json
import os
import signal
import threading
import traceback
from collections import Counter
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, NamedTuple, Optional

import pandas as pd
import structlog
from django.db import connections, transaction
from psycopg2 import sql as pg_sql  # type: ignore[import-untyped]

from api.models.Resource import Resource, ResourceDataTable, ResourceFileDetails
from api.models.ResourceSchema import ResourceSchema
from api.utils.data_table_names import (
    data_table_name,
    may_share_physical_table,
    physical_table_name,
)
from api.utils.file_utils import load_tabular_data, local_copy

logger = structlog.get_logger("dataspace.data_tables")

DATA_DB = "data_db"  # the connection name in settings.DATABASES

# Formats copied into a table (and so readable through the data API).
INDEXED_FORMATS = {"csv", "xls", "xlsx", "ods", "parquet", "feather", "json", "tsv"}

# How long a drop waits for readers holding the table before giving up.
DROP_LOCK_TIMEOUT = "5s"

# How long reading a file may take, where the platform lets us stop it.
LOAD_TIMEOUT_SECONDS = 60


class FileIdentity(NamedTuple):
    """Which stored file a build read: its storage name and SHA-256."""

    name: str
    sha256: Optional[str]


class LoadedFile(NamedTuple):
    """A resource's file read into a frame, with the identity of that file."""

    frame: pd.DataFrame
    file: FileIdentity


class NewerFileSaved(Exception):
    """Another upload saved a newer file while this one was being built."""


def get_sql_type(pandas_dtype: str) -> str:
    """The Postgres column type for a pandas dtype name (TEXT when unsure)."""
    if "int" in pandas_dtype:
        return "BIGINT"
    if "float" in pandas_dtype:
        return "DOUBLE PRECISION"
    if "datetime" in pandas_dtype:
        return "TIMESTAMP"
    if "bool" in pandas_dtype:
        return "BOOLEAN"
    return "TEXT"


_FIELD_FORMATS = {
    "BIGINT": "INTEGER",
    "DOUBLE PRECISION": "NUMBER",
    "TIMESTAMP": "DATE",
    "BOOLEAN": "BOOLEAN",
}


def error_fields(error: BaseException) -> Dict[str, Any]:
    """Log fields for an error: its class, Postgres error code and where it was raised.

    Never its message: database messages quote the offending value (a COPY
    error names the cell). ``where`` is the innermost frame in our own code
    ("data_tables.py:231 build_data_table"), which carries no data.
    """
    cause = error.__cause__ or error
    frames = traceback.extract_tb(error.__traceback__)
    ours = [f for f in frames if f"{os.sep}api{os.sep}" in f.filename] or frames
    where = (
        f"{os.path.basename(ours[-1].filename)}:{ours[-1].lineno} {ours[-1].name}" if ours else None
    )
    return {
        "error_type": type(error).__name__,
        "error_code": getattr(cause, "pgcode", None),
        "where": where,
    }


def is_inside_transaction() -> bool:
    """Whether the main database is already inside a transaction (an atomic block)."""
    return bool(transaction.get_connection().in_atomic_block)


def has_indexable_file(resource: Resource) -> bool:
    """Whether the resource has a stored file in a format that gets a table."""
    file_details = getattr(resource, "resourcefiledetails", None)
    if not file_details or not file_details.file:
        logger.info("data_index_skipped_no_file", resource_id=str(resource.id))
        return False
    file_format = (file_details.format or "").lower()
    if file_format not in INDEXED_FORMATS:
        logger.info("data_index_skipped_format", resource_id=str(resource.id), format=file_format)
        return False
    return True


def load_resource_frame(resource: Resource) -> Optional[LoadedFile]:
    """Read the resource's stored file into a frame and note which file it was.

    Column names are cleaned the way tables have always needed them: double
    quotes removed, line breaks and tabs turned into spaces, and names that
    then collide get "_1", "_2", ... suffixes.

    Returns None when the file can't be read, takes longer than
    LOAD_TIMEOUT_SECONDS, or has no rows (each case logged).
    """
    file_details = resource.resourcefiledetails
    identity = FileIdentity(file_details.file.name, file_details.sha256)
    try:
        with local_copy(file_details.file) as path:
            frame = _load_with_timeout(path, file_details.format.lower())
    except Exception as error:
        logger.error("data_index_load_failed", resource_id=str(resource.id), **error_fields(error))
        return None
    if frame is None:
        logger.error("data_index_load_failed", resource_id=str(resource.id), error_type="NoFrame")
        return None
    if frame.empty:
        logger.info("data_index_skipped_empty", resource_id=str(resource.id))
        return None
    frame.columns = pd.Index(_clean_column_names(list(frame.columns)))
    return LoadedFile(frame, identity)


def _load_with_timeout(path: str, file_format: str) -> Optional[pd.DataFrame]:
    # SIGALRM only works in a Unix process's main thread; elsewhere (a server
    # worker thread) the file loads without a limit, as it always has.
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "SIGALRM"):
        return load_tabular_data(path, file_format)

    def on_alarm(signum: int, frame: Any) -> None:
        raise TimeoutError(f"loading took longer than {LOAD_TIMEOUT_SECONDS} seconds")

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.alarm(LOAD_TIMEOUT_SECONDS)
    try:
        return load_tabular_data(path, file_format)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _clean_column_names(columns: List[Any]) -> List[str]:
    cleaned = [str(c).replace('"', "").replace("\n", " ").replace("\t", " ") for c in columns]
    seen: Counter = Counter()
    unique = []
    for name in cleaned:
        unique.append(f"{name}_{seen[name]}" if seen[name] else name)
        seen[name] += 1
    return unique


def stored_file_identity(resource: Resource) -> Optional[FileIdentity]:
    """The resource's current stored file, read fresh from the database."""
    row = (
        ResourceFileDetails.objects.filter(resource_id=resource.pk)
        .values_list("file", "sha256")
        .first()
    )
    return FileIdentity(*row) if row else None


def new_data_table_row(resource: Resource) -> ResourceDataTable:
    """An unsaved ResourceDataTable row for this upload, already carrying its table name."""
    row = ResourceDataTable(resource=resource)
    row.table_name = data_table_name(row.id)
    return row


def describe_data_table(resource: Resource, built_at: datetime) -> str:
    """The comment stored on a new table, so people browsing the data database know what it holds.

    JSON with the resource id and name, the dataset title and the build time;
    the migration command reads ``built_at`` to leave freshly built tables alone.
    """
    return json.dumps(
        {
            "resource_id": str(resource.id),
            "resource": resource.name,
            "dataset": resource.dataset.title,
            "built_at": built_at.isoformat(),
        },
        ensure_ascii=False,
    )


def build_data_table(table_name: str, frame: pd.DataFrame, comment: str) -> None:
    """Create a table holding every row of the frame, in one data-database transaction.

    Creates the table, copies the rows in through a temporary table, and
    stores the comment. Raises on any failure, and then nothing is left
    behind: a killed process or a bad value mid-copy rolls the whole table back.
    """
    table = pg_sql.Identifier(table_name)
    staging = pg_sql.Identifier(f"tmp_{table_name}")
    columns = pg_sql.SQL(", ").join(
        pg_sql.SQL("{} {}").format(
            pg_sql.Identifier(str(col)), pg_sql.SQL(get_sql_type(str(frame[col].dtype)))
        )
        for col in frame.columns
    )
    rows = StringIO()
    frame.to_csv(rows, index=False, header=False)
    rows.seek(0)

    with transaction.atomic(using=DATA_DB), connections[DATA_DB].cursor() as cursor:
        cursor.execute(pg_sql.SQL("CREATE TABLE {} ({})").format(table, columns))
        cursor.execute(
            pg_sql.SQL("CREATE TEMP TABLE {} (LIKE {}) ON COMMIT DROP").format(staging, table)
        )
        cursor.copy_expert(pg_sql.SQL("COPY {} FROM STDIN WITH CSV").format(staging), rows)
        cursor.execute(pg_sql.SQL("INSERT INTO {} SELECT * FROM {}").format(table, staging))
        cursor.execute(
            pg_sql.SQL("COMMENT ON TABLE {} IS {}").format(table, pg_sql.Literal(comment))
        )


def lock_resource(resource: Resource) -> None:
    """Lock the resource's row until the surrounding transaction ends.

    Two uploads of one resource then switch one after the other. A no-op on
    SQLite (tests); Postgres in production.
    """
    Resource.objects.select_for_update().only("id").get(pk=resource.pk)


def retire_data_table_row(resource: Resource) -> Optional[datetime]:
    """Delete the resource's current ResourceDataTable row, returning when it was created.

    Its table is dropped by the delete receiver once the surrounding
    transaction commits. Returns None when the resource had no row.
    """
    old = ResourceDataTable.objects.filter(resource_id=resource.pk).first()
    if old is None:
        return None
    created = old.created
    old.delete()
    return created


def save_data_table_row(row: ResourceDataTable, created: Optional[datetime]) -> None:
    """Save the new row, keeping the retired row's creation time when there was one.

    The data API picks a dataset's default table by creation time, so a
    re-upload keeps the dataset's default where it was.
    """
    row.save(force_insert=True)
    if created is not None:
        ResourceDataTable.objects.filter(pk=row.pk).update(created=created)
        row.created = created


def rebuild_resource_schema(resource: Resource, frame: pd.DataFrame) -> None:
    """Replace the resource's column rows with one per frame column.

    Each column's type comes from the frame. Descriptions people wrote are
    carried over to columns with the same name; new columns get
    "Description of column <name>".

    Errors escape: inside the switch transaction a swallowed database error
    would silently roll the whole switch back. A header longer than the column
    row allows is refused up front (ValueError naming its position), the same
    outcome Postgres would give, on every database.
    """
    max_length = ResourceSchema._meta.get_field("field_name").max_length or 255
    for position, column in enumerate(frame.columns, start=1):
        if len(str(column)) > max_length:
            raise ValueError(f"column {position} header is longer than {max_length} characters")

    existing = ResourceSchema.objects.filter(resource=resource)
    descriptions = {
        name: description
        for name, description in existing.values_list("field_name", "description")
        if description is not None
    }
    existing.delete()
    for column in frame.columns:
        sql_type = get_sql_type(str(frame[column].dtype))
        ResourceSchema.objects.create(
            resource=resource,
            field_name=column,
            format=_FIELD_FORMATS.get(sql_type, "STRING"),
            description=descriptions.get(column, f"Description of column {column}"),
        )


def data_table_row_exists(row_id: Any) -> bool:
    """Whether a ResourceDataTable row with this id is saved."""
    return ResourceDataTable.objects.filter(pk=row_id).exists()


def drop_data_table(table_name: str) -> bool:
    """Drop a table from the data database; never raises.

    Waits at most DROP_LOCK_TIMEOUT for readers holding the table. A failure
    is logged with the table name and swallowed — the table is left behind as
    an orphan for ``migrate_data_table_names`` to report. Returns whether the
    drop went through (a table that was already gone counts as dropped).
    """
    try:
        with transaction.atomic(using=DATA_DB), connections[DATA_DB].cursor() as cursor:
            cursor.execute(
                pg_sql.SQL("SET LOCAL lock_timeout = {}").format(pg_sql.Literal(DROP_LOCK_TIMEOUT))
            )
            cursor.execute(
                pg_sql.SQL("DROP TABLE IF EXISTS {}").format(pg_sql.Identifier(table_name))
            )
    except Exception as error:
        logger.error("data_table_drop_failed", table_name=table_name, **error_fields(error))
        return False
    logger.info("data_table_dropped", table_name=table_name)
    return True


def drop_data_table_if_unshared(table_name: str, row_id: Any) -> None:
    """Drop a deleted row's table, unless another row still uses the same physical table.

    Only names from before per-upload tables can share one (Postgres cut two
    long names to the same 63 bytes); for those, the table stays until its last
    row is gone. Query: ``table_name LIKE '<physical>%'`` on the unique
    table_name index — a sequential scan on some collations, over one row per
    tabular resource. Never raises.
    """
    try:
        shared = may_share_physical_table(table_name) and _another_row_uses(table_name, row_id)
    except Exception as error:
        logger.error("data_table_drop_failed", table_name=table_name, **error_fields(error))
        return
    if shared:
        logger.info("data_table_drop_skipped_shared", table_name=table_name, row_id=str(row_id))
        return
    drop_data_table(table_name)


def _another_row_uses(table_name: str, row_id: Any) -> bool:
    physical = physical_table_name(table_name)
    candidates = (
        ResourceDataTable.objects.filter(table_name__startswith=physical)
        .exclude(pk=row_id)
        .values_list("table_name", flat=True)
    )
    return any(physical_table_name(name) == physical for name in candidates)
