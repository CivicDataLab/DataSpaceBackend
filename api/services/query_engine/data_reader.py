"""The only way query-engine code reads the data database.

``run_read_only_query`` runs one statement in its own short transaction:
``SET TRANSACTION READ ONLY``, then transaction-local ``statement_timeout``
and ``lock_timeout`` (``set_config(..., true)``, so nothing stays on a reused
connection), then the statement with its parameter list (always a list, even
empty: column names carry doubled ``%`` from ``_column_ident``). It returns
the rows plus the exact SQL that ran (``cursor.mogrify``), for citation.

Every statement it is given must end with ``LIMIT max_rows + 1``
(``with_row_limit``), so memory is bounded before rows reach Python; more
than that many rows back is refused as a bug. ``truncated`` means more than
``max_rows`` came back.

Database errors become typed errors by Postgres error code, never carrying the
database's message (it can quote values):
57014 → QueryTooSlow; 55P03 (lock wait), 42P01 (table gone), 42703 (column
gone) → DataRefreshing; 25006 (a write in a read-only transaction) →
InternalQueryError, logged as an error; anything else → QueryFailed.

Docs: api/views/query_engine/architecture.md
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

import structlog
from django.conf import settings
from django.db import DatabaseError, connections, transaction
from psycopg2 import sql as pg_sql  # type: ignore[import-untyped]

from api.services.query_engine.errors import (
    DataRefreshing,
    InternalQueryError,
    QueryEngineError,
    QueryFailed,
    QueryTooSlow,
)
from api.utils.data_tables import DATA_DB, error_fields

logger = structlog.get_logger("dataspace.query_engine.data_reader")

# Postgres allows at most 1,600 columns per table.
MAX_TABLE_COLUMNS = 1600

_REFRESHING_CODES = {"55P03", "42P01", "42703"}


@dataclass(frozen=True)
class ReadResult:
    columns: List[str]
    rows: List[Tuple[Any, ...]]
    sql: str
    truncated: bool


def with_row_limit(query: pg_sql.Composable, max_rows: int) -> pg_sql.Composed:
    """``query`` with ``LIMIT max_rows + 1`` appended (the extra row shows truncation)."""
    return pg_sql.Composed([query, pg_sql.SQL(" LIMIT "), pg_sql.Literal(int(max_rows) + 1)])


def run_read_only_query(
    query: pg_sql.Composable,
    params: Sequence[Any],
    *,
    timeout_ms: int,
    max_rows: int,
) -> ReadResult:
    """Run one SELECT read-only with time limits; return its rows and the SQL that ran."""
    connection = connections[DATA_DB]
    try:
        with transaction.atomic(using=DATA_DB, durable=True), connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, true), "
                "set_config('lock_timeout', %s, true)",
                [str(int(timeout_ms)), str(int(settings.QE_LOCK_TIMEOUT_MS))],
            )
            sql_text = cursor.mogrify(query, list(params)).decode("utf-8")
            cursor.execute(query, list(params))
            columns = [column[0] for column in cursor.description or []]
            rows = cursor.fetchall()
    except DatabaseError as error:
        raise classify_db_error(error) from error
    if len(rows) > max_rows + 1:
        logger.error("qe_read_without_row_limit", rows=len(rows), max_rows=max_rows)
        raise InternalQueryError(reason="statement_without_row_limit")
    return ReadResult(
        columns=columns,
        rows=[tuple(row) for row in rows[:max_rows]],
        sql=sql_text,
        truncated=len(rows) > max_rows,
    )


def classify_db_error(error: BaseException) -> QueryEngineError:
    """The typed error for a database failure, chosen by its Postgres error code."""
    cause = error.__cause__ or error
    pgcode = getattr(cause, "pgcode", None)
    if pgcode == "57014":
        return QueryTooSlow(reason="statement_timeout")
    if pgcode in _REFRESHING_CODES:
        return DataRefreshing(reason="table_changed", pgcode=pgcode)
    if pgcode == "25006":
        logger.error("qe_write_attempt_blocked", **error_fields(error))
        return InternalQueryError(reason="write_attempt_blocked")
    logger.warning("qe_query_failed", **error_fields(error))
    return QueryFailed(reason="database_error", pgcode=pgcode)


def read_table_columns(table_name: str) -> Dict[str, str]:
    """The table's columns as Postgres stores them: physical name → storage type, in order.

    Read from the catalogue (pg_attribute via ``to_regclass(quote_ident(name))``,
    so names with hyphens or capitals work). Raises DataRefreshing when the
    table doesn't exist (dropped by a re-upload in the meantime).
    """
    query = with_row_limit(
        pg_sql.SQL(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "WHERE a.attrelid = to_regclass(quote_ident(%s)) AND a.attnum > 0 "
            "AND NOT a.attisdropped ORDER BY a.attnum"
        ),
        MAX_TABLE_COLUMNS,
    )
    result = run_read_only_query(
        query, [table_name], timeout_ms=settings.QE_QUERY_TIMEOUT_MS, max_rows=MAX_TABLE_COLUMNS
    )
    if not result.rows:
        raise DataRefreshing(reason="table_missing")
    return {str(name): str(storage_type) for name, storage_type in result.rows}
