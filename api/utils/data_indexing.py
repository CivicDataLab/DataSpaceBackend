"""Copying tabular uploads into the data database, and reading them back.

The upload flow is ``index_resource_data`` below; its helpers live in
./data_tables.py. The rest of this module reads the tables (row count,
preview, column list, the data API's filtered fetch, chart queries); every
reader looks the table up from the resource's ResourceDataTable row.

Docs: ./data_indexing_architecture.md
"""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import structlog
from django.db import connections, transaction
from django.db.utils import ProgrammingError
from django.utils import timezone
from psycopg2 import sql as pg_sql  # type: ignore[import-untyped]

from api.models.Resource import Resource, ResourceDataTable
from api.models.ResourceSchema import ResourceSchema
from api.types.type_preview_data import PreviewData
from api.utils.data_tables import (  # noqa: F401 — DATA_DB, INDEXED_FORMATS, get_sql_type re-exported
    DATA_DB,
    INDEXED_FORMATS,
    NewerFileSaved,
    build_data_table,
    data_table_row_exists,
    describe_data_table,
    drop_data_table,
    error_fields,
    get_sql_type,
    has_indexable_file,
    is_inside_transaction,
    load_resource_frame,
    lock_resource,
    new_data_table_row,
    rebuild_resource_schema,
    retire_data_table_row,
    save_data_table_row,
    stored_file_identity,
)
from api.utils.file_utils import local_copy

logger = structlog.get_logger("dataspace.data_indexing")

# Formats counted by parsing the file directly (not indexed into DB)
FILE_COUNT_FORMATS = {"yml", "yaml", "xml"}

# Allowed comparison operators for column-based filtering on indexed data.
# Maps operator suffix -> (sql_template_with_{ph}_placeholder, value_transformer)
_FILTER_OPERATORS: Dict[str, Tuple[str, Any]] = {
    "eq": ("= %s", lambda v: v),
    "ne": ("<> %s", lambda v: v),
    "gt": ("> %s", lambda v: v),
    "gte": (">= %s", lambda v: v),
    "lt": ("< %s", lambda v: v),
    "lte": ("<= %s", lambda v: v),
    "in": ("= ANY(%s)", lambda v: list(v) if not isinstance(v, list) else v),
    "nin": ("<> ALL(%s)", lambda v: list(v) if not isinstance(v, list) else v),
    "contains": ("LIKE %s", lambda v: f"%{v}%"),
    "icontains": ("ILIKE %s", lambda v: f"%{v}%"),
    "startswith": ("LIKE %s", lambda v: f"{v}%"),
    "istartswith": ("ILIKE %s", lambda v: f"{v}%"),
    "endswith": ("LIKE %s", lambda v: f"%{v}"),
    "iendswith": ("ILIKE %s", lambda v: f"%{v}"),
    "isnull": ("IS NULL", None),  # value ignored
    "notnull": ("IS NOT NULL", None),
}


def index_resource_data(resource: Resource) -> Optional[ResourceDataTable]:
    """Copy a resource's tabular file into a table of its own in the data database.

    Every upload gets a new table, named from its new ResourceDataTable row.
    The table is built in full first; then one main-database commit points the
    resource at it and rebuilds the column list. The old table is dropped after
    that commit by the row's delete receiver. Readers see the complete old data
    until the commit, then the complete new data. If anything fails, the old
    data stays as it was and this build's table is dropped.

    Must be called outside any transaction, so "committed" really means
    committed. Returns the new ResourceDataTable, or None when the resource
    was not switched over.
    """
    resource_id = str(resource.id)

    # Refuse to run inside someone else's transaction: the switch would only release a savepoint.
    if is_inside_transaction():
        logger.error("data_index_refused_inside_transaction", resource_id=resource_id)
        return None

    # Only supported tabular files (csv, xlsx, parquet, ...) get a table.
    if not has_indexable_file(resource):
        return None

    # Read the file into a frame, remembering exactly which stored file it was.
    loaded = load_resource_frame(resource)
    if loaded is None:
        return None

    # This upload's own row, and with it its own table name.
    new_row = new_data_table_row(resource)
    switched = False
    try:
        # Build the complete new table; readers keep using the old one meanwhile.
        build_data_table(
            new_row.table_name, loaded.frame, describe_data_table(resource, built_at=timezone.now())
        )

        # Switch the resource over to the new table in one commit.
        with transaction.atomic():
            # Hold the resource, so two uploads of it switch one after the other.
            lock_resource(resource)

            # If a newer file was saved while we built, that upload wins: back off.
            if stored_file_identity(resource) != loaded.file:
                raise NewerFileSaved()

            # Retire the old row; its table is dropped once this commits.
            previous_created = retire_data_table_row(resource)

            # Point the resource at the new table, keeping its place as the dataset's default.
            save_data_table_row(new_row, created=previous_created)

            # Rebuild the column list, keeping the descriptions people wrote.
            rebuild_resource_schema(resource, loaded.frame)

        # It only counts as switched if the new row really is there after the commit.
        switched = data_table_row_exists(new_row.pk)
        if not switched:
            logger.error("data_index_switch_not_saved", resource_id=resource_id)
    except NewerFileSaved:
        logger.info("data_index_skipped_newer_file", resource_id=resource_id)
    except Exception as error:
        logger.error("data_index_failed", resource_id=resource_id, **error_fields(error))
    finally:
        # Anything short of a confirmed switch leaves this build's table unused: drop it.
        if not switched:
            drop_data_table(new_row.table_name)

    if not switched:
        return None
    logger.info("data_index_switched", resource_id=resource_id, table_name=new_row.table_name)
    return new_row


def query_resource_data(resource: Resource, query: str) -> Optional[pd.DataFrame]:
    """Query data from a resource's indexed table."""
    try:
        data_table = ResourceDataTable.objects.get(resource=resource)
        with connections[DATA_DB].cursor() as cursor:
            cursor.execute(query.replace("{{table}}", f'"{data_table.table_name}"'))
            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()
            return pd.DataFrame(data, columns=columns)
    except (ResourceDataTable.DoesNotExist, ProgrammingError) as e:
        import traceback

        logger.error(
            f"Error querying resource {resource.id} with query {query} : {str(e)} , traceback: {traceback.format_exc()}"
        )
        return None


def get_row_count(resource: Resource) -> int:
    """Get the number of rows in the table."""
    try:
        # First check if the data table exists without making a database connection
        try:
            data_table = ResourceDataTable.objects.get(resource=resource)
        except ResourceDataTable.DoesNotExist:
            return 0

        # Set a timeout for the database query
        import time

        from django.db import connection

        # Use a timeout to prevent long-running queries
        with connections[DATA_DB].cursor() as cursor:
            # Set statement timeout to 2 seconds
            cursor.execute("SET statement_timeout = 2000")
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{data_table.table_name}"')
                result = cursor.fetchone()
                return int(result[0]) if result else 0
            except Exception as query_error:
                logger.error(
                    f"Query timeout or error for resource {resource.id}: {str(query_error)}"
                )
                return 0
    except Exception as e:
        import traceback

        error_tb = traceback.format_exc()
        logger.error(f"Error getting row count for resource {resource.id}:\n{str(e)}\n{error_tb}")
        return 0


def get_entry_count_from_file(resource: Resource) -> int:
    """Count entries in yml/yaml/xml files by parsing the file directly."""
    try:
        file_details = getattr(resource, "resourcefiledetails", None)
        if not file_details:
            return 0

        fmt = file_details.format.lower()
        if fmt not in FILE_COUNT_FORMATS:
            return 0

        with local_copy(file_details.file) as filepath:
            if fmt in ("yml", "yaml"):
                import yaml

                with open(filepath, "r") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, list):
                    return len(data)
                if isinstance(data, dict):
                    for v in data.values():
                        if isinstance(v, list):
                            return len(v)
                    return len(data)
                return 0

            import xml.etree.ElementTree as ET

            root = ET.parse(filepath).getroot()
            return len(list(root))
    except Exception as e:
        logger.error(f"Error counting entries from file for resource {resource.id}: {str(e)}")
        return 0


def get_preview_data(resource: Resource) -> Optional[PreviewData]:
    try:
        if not resource.preview_enabled:
            return None

        preview_details = getattr(resource, "preview_details", None)
        if not preview_details:
            return None

        # First check if the data table exists without making a database connection
        try:
            data_table = ResourceDataTable.objects.get(resource=resource)
        except ResourceDataTable.DoesNotExist:
            logger.info(f"No data table exists for resource {resource.id}")
            return None

        is_all_entries = getattr(preview_details, "is_all_entries", False)
        start_entry = getattr(preview_details, "start_entry", 0)
        end_entry = getattr(
            preview_details, "end_entry", 10
        )  # Default to showing 10 rows if not specified

        # Use a timeout to prevent long-running queries
        with connections[DATA_DB].cursor() as cursor:
            # Set statement timeout to 3 seconds
            cursor.execute("SET statement_timeout = 3000")

            try:
                if is_all_entries:
                    # For safety, always limit the number of rows returned even for 'all entries'
                    cursor.execute(f'SELECT * FROM "{data_table.table_name}" LIMIT 1000')
                else:
                    # Ensure we have valid integer values for the calculation
                    start = int(start_entry) if start_entry is not None else 0
                    end = int(end_entry) if end_entry is not None else 10
                    limit = min(end - start + 1, 1000)  # Cap at 1000 rows for safety
                    cursor.execute(
                        f'SELECT * FROM "{data_table.table_name}" LIMIT {limit} OFFSET {start}'
                    )

                columns = [desc[0] for desc in cursor.description]
                data = cursor.fetchall()
                # Convert tuples to lists and sanitize None values to empty strings
                rows = [[cell if cell is not None else "" for cell in row] for row in data]
                return PreviewData(columns=columns, rows=rows)
            except Exception as query_error:
                logger.error(
                    f"Query timeout or error for resource {resource.id}: {str(query_error)}"
                )
                return None
    except Exception as e:
        import traceback

        logger.error(
            f"Error getting preview data for resource {resource.id}: {str(e)}, traceback: {traceback.format_exc()}"
        )
        return None


# Maximum rows that can be returned in a single fetch_resource_data call
MAX_FETCH_LIMIT = 10000
DEFAULT_FETCH_LIMIT = 100


class DataFetchError(Exception):
    """Raised when fetch_resource_data receives invalid input."""


def get_resource_columns(resource: Resource) -> List[str]:
    """Return the list of indexed column names for a resource.

    Falls back to inspecting the data_db table if no ResourceSchema rows exist.
    """
    cols = list(
        ResourceSchema.objects.filter(resource=resource).values_list("field_name", flat=True)
    )
    if cols:
        return cols
    # Fallback: introspect the table directly
    try:
        data_table = ResourceDataTable.objects.get(resource=resource)
        with connections[DATA_DB].cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s ORDER BY ordinal_position",
                [data_table.table_name],
            )
            return [row[0] for row in cursor.fetchall()]
    except ResourceDataTable.DoesNotExist:
        return []


def _column_ident(column: str) -> pg_sql.Identifier:
    """Quote a column name for a query that will be run with parameters.

    psycopg2 fills in ``%s`` placeholders by %-formatting the whole query
    text, quoted names included, so a header like "Literacy rate (%)" breaks
    the query unless its ``%`` is doubled. Every query in
    ``fetch_resource_data`` is run with a parameter list, so the doubled
    ``%%`` always comes back out as ``%``.
    """
    return pg_sql.Identifier(column.replace("%", "%%"))


def _parse_filter_key(key: str) -> Tuple[str, str]:
    """Split 'col__op' style filter key into (column, op). Defaults op to 'eq'."""
    if "__" in key:
        col, op = key.rsplit("__", 1)
        if op not in _FILTER_OPERATORS:
            # No valid operator suffix — treat full key as column with eq
            return key, "eq"
        return col, op
    return key, "eq"


def _build_where_clause(
    filters: Dict[str, Any], allowed_columns: List[str]
) -> Tuple[pg_sql.Composable, List[Any]]:
    """Build a parameterized WHERE clause from a filters dict.

    Filters are of the form ``{"column": value}`` for equality, or
    ``{"column__op": value}`` for other operators. Unknown columns are rejected.
    """
    if not filters:
        return pg_sql.SQL(""), []

    allowed_set = set(allowed_columns)
    clauses: List[pg_sql.Composable] = []
    params: List[Any] = []

    for raw_key, value in filters.items():
        col, op = _parse_filter_key(raw_key)
        if col not in allowed_set:
            raise DataFetchError(f"Unknown filter column: {col}")
        op_template, transformer = _FILTER_OPERATORS[op]

        col_ident = _column_ident(col)
        if op in ("isnull", "notnull"):
            # Boolean toggle: isnull=true means IS NULL, isnull=false means IS NOT NULL
            truthy = value not in (False, "false", "False", 0, "0", None)
            sql_op = "IS NULL" if (op == "isnull") == truthy else "IS NOT NULL"
            clauses.append(pg_sql.SQL("{col} {op}").format(col=col_ident, op=pg_sql.SQL(sql_op)))
            continue

        # Compose: <col> <op_template> (where op_template contains %s placeholders)
        clauses.append(pg_sql.SQL("{col} ").format(col=col_ident) + pg_sql.SQL(op_template))
        params.append(transformer(value) if transformer else value)

    where_sql = pg_sql.SQL(" WHERE ") + pg_sql.SQL(" AND ").join(clauses)
    return where_sql, params


def _build_order_by(order_by: Optional[List[str]], allowed_columns: List[str]) -> pg_sql.Composable:
    """Build a parameterised ORDER BY clause. Each entry may be 'col' or '-col'."""
    if not order_by:
        return pg_sql.SQL("")
    allowed_set = set(allowed_columns)
    parts: List[pg_sql.Composable] = []
    for item in order_by:
        direction = "ASC"
        col = item
        if item.startswith("-"):
            direction = "DESC"
            col = item[1:]
        elif item.startswith("+"):
            col = item[1:]
        if col not in allowed_set:
            raise DataFetchError(f"Unknown order_by column: {col}")
        parts.append(pg_sql.SQL("{col} ").format(col=_column_ident(col)) + pg_sql.SQL(direction))
    return pg_sql.SQL(" ORDER BY ") + pg_sql.SQL(", ").join(parts)


def _build_select_list(columns: List[str]) -> pg_sql.Composable:
    """Build the comma-separated list of quoted column names to SELECT."""
    return pg_sql.SQL(", ").join(_column_ident(c) for c in columns)


def fetch_resource_data(
    resource: Resource,
    filters: Optional[Dict[str, Any]] = None,
    columns: Optional[List[str]] = None,
    limit: int = DEFAULT_FETCH_LIMIT,
    offset: int = 0,
    order_by: Optional[List[str]] = None,
    count: bool = True,
) -> Dict[str, Any]:
    """Fetch indexed data for a Resource from data_db with column-level filtering.

    Returns a dict::

        {
            "columns": [...],  # selected column names
            "rows": [[...], ...],  # list of rows (one list per row)
            "total": <int or None>,  # total matching rows (None if count=False)
            "limit": <int>,
            "offset": <int>,
        }

    Args:
        resource: The Resource whose indexed data should be fetched.
        filters: Optional dict of ``{"col": val}`` or ``{"col__op": val}`` filters.
        columns: Optional list of columns to project. Defaults to all columns.
        limit: Max rows to return (capped at MAX_FETCH_LIMIT).
        offset: Number of rows to skip.
        order_by: Optional list of columns; prefix with ``-`` for DESC.
        count: When True (default) also returns the total matching row count.

    Raises:
        DataFetchError: If the resource has no indexed data, or filters/columns
            reference unknown columns.
    """
    try:
        data_table = ResourceDataTable.objects.get(resource=resource)
    except ResourceDataTable.DoesNotExist:
        raise DataFetchError(f"Resource {resource.id} has no indexed data table")

    allowed_columns = get_resource_columns(resource)
    if not allowed_columns:
        raise DataFetchError(f"Resource {resource.id} has no schema/columns available")

    # Validate and resolve projected columns
    if columns:
        unknown = [c for c in columns if c not in allowed_columns]
        if unknown:
            raise DataFetchError(f"Unknown columns: {unknown}")
        select_columns = columns
    else:
        select_columns = allowed_columns

    # Clamp pagination
    if limit is None or limit <= 0:
        limit = DEFAULT_FETCH_LIMIT
    limit = min(int(limit), MAX_FETCH_LIMIT)
    offset = max(int(offset or 0), 0)

    table_ident = pg_sql.Identifier(data_table.table_name)
    cols_sql = _build_select_list(select_columns)
    where_sql, params = _build_where_clause(filters or {}, allowed_columns)
    order_sql = _build_order_by(order_by, allowed_columns)

    select_query = (
        pg_sql.SQL("SELECT ")
        + cols_sql
        + pg_sql.SQL(" FROM ")
        + table_ident
        + where_sql
        + order_sql
        + pg_sql.SQL(" LIMIT %s OFFSET %s")
    )

    total: Optional[int] = None
    with connections[DATA_DB].cursor() as cursor:
        # Safety: cap query time
        cursor.execute("SET statement_timeout = 10000")

        if count:
            count_query = pg_sql.SQL("SELECT COUNT(*) FROM ") + table_ident + where_sql
            cursor.execute(count_query, params)
            row = cursor.fetchone()
            total = int(row[0]) if row else 0

        cursor.execute(select_query, params + [limit, offset])
        result_columns = [desc[0] for desc in cursor.description]
        rows = [list(r) for r in cursor.fetchall()]

    return {
        "columns": result_columns,
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
