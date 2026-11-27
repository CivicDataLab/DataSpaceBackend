"""Layer 1 (real Postgres data database): the one read-only executor (R1–R8, Q5).

Each test builds a small table directly; the executor doesn't care how a table
was made. The pgcode mapping (Q5) is also checked without a database.
"""

import time
from typing import Any

import psycopg2
import pytest
from django.db import connections
from psycopg2 import sql as pg_sql

from api.services.query_engine.data_reader import (
    classify_db_error,
    read_table_columns,
    run_read_only_query,
    with_row_limit,
)
from api.utils.data_indexing import _column_ident
from api.services.query_engine.errors import (
    DataRefreshing,
    InternalQueryError,
    QueryFailed,
    QueryTooSlow,
)
from tests.data_index.support import DATA_DB, uses_data_db

TABLE = "qe_reader_test"


def make_table() -> None:
    with connections[DATA_DB].cursor() as cursor:
        cursor.execute(
            f'CREATE TABLE "{TABLE}" ("District" text, "IMR (%)" double precision, n bigint)'
        )
        cursor.execute(
            f'INSERT INTO "{TABLE}" VALUES '
            "('Kamrup', 32.5, 1), ('Nagaon', 40.0, 2), ('Dibrugarh', 28.0, 3)"
        )


def select_all(where: str = "") -> pg_sql.Composed:
    return pg_sql.SQL("SELECT {c}, {imr} FROM {t}" + where).format(
        c=pg_sql.Identifier("District"),
        imr=_column_ident("IMR (%)"),
        t=pg_sql.Identifier(TABLE),
    )


def setting(name: str) -> str:
    with connections[DATA_DB].cursor() as cursor:
        cursor.execute(f"SHOW {name}")
        return str(cursor.fetchone()[0])


@uses_data_db
def test_returns_columns_rows_and_the_sql_that_ran() -> None:
    make_table()
    query = with_row_limit(select_all(" WHERE {c} = %s ORDER BY 1"), max_rows=10)

    result = run_read_only_query(query, ["Kamrup"], timeout_ms=1000, max_rows=10)

    assert result.columns == ["District", "IMR (%)"]
    assert result.rows == [("Kamrup", 32.5)]
    assert result.truncated is False
    assert result.sql == (
        'SELECT "District", "IMR (%)" FROM "qe_reader_test" '
        "WHERE \"District\" = 'Kamrup' ORDER BY 1 LIMIT 11"
    )


@uses_data_db
@pytest.mark.parametrize(
    "statement",
    [
        f"INSERT INTO \"{TABLE}\" VALUES ('X', 1, 9)",
        f'UPDATE "{TABLE}" SET n = 0',
        f'DROP TABLE "{TABLE}"',
    ],
    ids=["insert", "update", "drop"],
)
def test_every_write_fails_as_read_only_and_changes_nothing(statement: str) -> None:
    make_table()

    with pytest.raises(InternalQueryError):
        run_read_only_query(pg_sql.SQL(statement), [], timeout_ms=1000, max_rows=10)

    with connections[DATA_DB].cursor() as cursor:
        cursor.execute(f'SELECT count(*), sum(n) FROM "{TABLE}"')
        assert cursor.fetchone() == (3, 6)


@uses_data_db
def test_a_statement_past_its_timeout_is_too_slow() -> None:
    with pytest.raises(QueryTooSlow):
        run_read_only_query(pg_sql.SQL("SELECT pg_sleep(1)"), [], timeout_ms=50, max_rows=1)


@uses_data_db
def test_timeouts_never_stay_on_the_connection() -> None:
    make_table()
    before = (setting("statement_timeout"), setting("lock_timeout"))

    with pytest.raises(QueryTooSlow):
        run_read_only_query(pg_sql.SQL("SELECT pg_sleep(1)"), [], timeout_ms=50, max_rows=1)
    assert (setting("statement_timeout"), setting("lock_timeout")) == before

    run_read_only_query(with_row_limit(select_all(), 5), [], timeout_ms=1234, max_rows=5)
    assert (setting("statement_timeout"), setting("lock_timeout")) == before


@uses_data_db
def test_a_locked_table_reads_as_data_refreshing_within_the_lock_timeout(
    settings: Any,
) -> None:
    make_table()
    settings.QE_LOCK_TIMEOUT_MS = 200
    params = connections[DATA_DB].get_connection_params()
    other = psycopg2.connect(**params)
    try:
        with other.cursor() as cursor:
            cursor.execute(f'LOCK TABLE "{TABLE}" IN ACCESS EXCLUSIVE MODE')
        started = time.monotonic()
        with pytest.raises(DataRefreshing):
            run_read_only_query(with_row_limit(select_all(), 5), [], timeout_ms=5000, max_rows=5)
        assert time.monotonic() - started < 2
    finally:
        other.rollback()
        other.close()


@uses_data_db
def test_reading_a_dropped_table_is_data_refreshing() -> None:
    with pytest.raises(DataRefreshing):
        run_read_only_query(with_row_limit(select_all(), 5), [], timeout_ms=1000, max_rows=5)


@uses_data_db
def test_an_undefined_column_is_data_refreshing() -> None:
    make_table()
    query = pg_sql.SQL("SELECT {} FROM {} LIMIT 2").format(
        pg_sql.Identifier("gone"), pg_sql.Identifier(TABLE)
    )
    with pytest.raises(DataRefreshing):
        run_read_only_query(query, [], timeout_ms=1000, max_rows=1)


@uses_data_db
def test_the_row_limit_is_in_the_sql_and_marks_truncation() -> None:
    make_table()
    query = with_row_limit(select_all(" ORDER BY 1"), max_rows=2)

    result = run_read_only_query(query, [], timeout_ms=1000, max_rows=2)

    assert result.sql.endswith("LIMIT 3")
    assert len(result.rows) == 2
    assert result.truncated is True


@uses_data_db
def test_refuses_a_statement_that_returns_more_than_its_limit() -> None:
    make_table()
    with pytest.raises(InternalQueryError):
        run_read_only_query(select_all(), [], timeout_ms=1000, max_rows=1)


@uses_data_db
def test_reads_storage_types_by_physical_name() -> None:
    make_table()
    assert read_table_columns(TABLE) == {
        "District": "text",
        "IMR (%)": "double precision",
        "n": "bigint",
    }


@uses_data_db
def test_reading_columns_of_a_missing_table_is_data_refreshing() -> None:
    with pytest.raises(DataRefreshing):
        read_table_columns("rdt_missing")


class PostgresError(Exception):
    pgcode: Any = None


class TestClassifyDbError:
    @pytest.mark.parametrize(
        "pgcode,expected",
        [
            ("57014", QueryTooSlow),
            ("55P03", DataRefreshing),
            ("42P01", DataRefreshing),
            ("42703", DataRefreshing),
            ("25006", InternalQueryError),
            ("22P02", QueryFailed),
            (None, QueryFailed),
        ],
    )
    def test_maps_each_postgres_code(self, pgcode: Any, expected: type) -> None:
        cause = PostgresError("database said something with a value in it")
        cause.pgcode = pgcode
        error = Exception("wrapped")
        error.__cause__ = cause
        mapped = classify_db_error(error)
        assert type(mapped) is expected
        assert "value in it" not in mapped.message
