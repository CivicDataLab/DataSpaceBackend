"""The statements that read a data table's column statistics, and turning their rows into numbers.

Columns are read in batches of at most 25, each batch with up to four bounded
statements, all through the read-only executor with the profile timeout:

1. **aggregates** (one row, cheap): per column the non-null and distinct
   counts; min / max / mean for numbers and dates; for text, how many values
   look numeric and how many are placeholders (NA, N/A, -, --, nil, ..).
2. **numbers written as text** (one row, only for columns step 1 found to be
   such): their min / max / mean through the guarded cast.
3. **values**: every distinct value with its count (most common first, ties by
   value) for columns with at most 1,000 distinct values; for numeric-looking
   text with more, its 5 most common non-numeric tokens.
4. **samples**: the first 20 rows of columns with more than 1,000 distinct
   values, for examples.

Each statement ends with ``LIMIT max_rows + 1``. A batch that times out is
retried in batches of 5, then one column at a time; a column that still times
out, or that is reached after the table's time budget, is reported as
unavailable rather than failing the profile, so one wide or huge table still
gets a partial profile (retried later). Each timeout is logged. Other
database errors are raised.

Numbers come back as JSON numbers rounded to 6 decimals; infinite or NaN
values become null and are reported, so they can be noted in the profile.
Cell values are cut to 200 characters. Column names go through
``_column_ident`` and regexes and placeholder lists are parameters.

Docs: api/views/query_engine/architecture.md
"""

import datetime
import math
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

import structlog
from django.conf import settings
from psycopg2 import sql as pg_sql  # type: ignore[import-untyped]

from api.services.query_engine.column_roles import (
    KIND_NUMERIC_TEXT,
    NUMERIC_TYPES,
    PLACEHOLDERS,
    detect_kind,
)
from api.services.query_engine.data_reader import run_read_only_query, with_row_limit
from api.services.query_engine.errors import QueryTooSlow
from api.utils.data_indexing import _column_ident

logger = structlog.get_logger("dataspace.query_engine.profiles")

STATS_BATCH_COLUMNS = 25
# A timed-out batch is retried in batches of these sizes, then given up.
SPLIT_SIZES = (5, 1)
VALUES_CAP = 1000
ODD_TOKENS = 5
VALUE_CHARS = 200
SAMPLE_ROWS = 20
DECIMALS = 6

# A text value that looks like a number: "1,23,456", "-12.5", "45 %".
NUMERIC_TEXT_RE = r"^\s*-?[0-9][0-9,]*(\.[0-9]+)?\s*%?\s*$"
# What is stripped from such a value before it is read as a number.
NUMERIC_TEXT_STRIP_RE = r"[,%[:space:]]"
_NUMERIC_TEXT = re.compile(NUMERIC_TEXT_RE)


@dataclass(frozen=True)
class ColumnRef:
    """A column to read: its full header (as uploaded) and its storage type."""

    header: str
    storage_type: str

    @property
    def is_number(self) -> bool:
        return self.storage_type.startswith(NUMERIC_TYPES)

    @property
    def is_text(self) -> bool:
        return self.storage_type == "text"

    @property
    def is_date(self) -> bool:
        return self.storage_type.startswith("timestamp") or self.storage_type == "date"


def numeric_text_cast(column: pg_sql.Composable) -> Tuple[pg_sql.Composed, List[Any]]:
    """The guarded cast of a numeric-looking text column: its number, or NULL when it isn't one."""
    expression = pg_sql.SQL(
        "(CASE WHEN {c} ~ %s THEN regexp_replace({c}, %s, '', 'g')::numeric END)"
    ).format(c=column)
    return expression, [NUMERIC_TEXT_RE, NUMERIC_TEXT_STRIP_RE]


def to_json_number(value: Any) -> Tuple[Any, bool]:
    """A database value as JSON: (value, was_non_finite). Decimals and floats rounded to 6 places."""
    if isinstance(value, bool) or value is None:
        return value, False
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None, True
        value = float(value)
    if isinstance(value, float):
        if math.isinf(value) or math.isnan(value):
            return None, True
        return round(value, DECIMALS), False
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat(), False
    return value, False


def count_rows(table: str) -> int:
    """How many rows the table has."""
    query = with_row_limit(
        pg_sql.SQL("SELECT count(*) FROM {}").format(pg_sql.Identifier(table)), 1
    )
    result = run_read_only_query(query, [], timeout_ms=settings.QE_PROFILE_TIMEOUT_MS, max_rows=1)
    return int(result.rows[0][0])


def read_column_stats(
    table: str,
    columns: Sequence[ColumnRef],
    deadline: Optional[float] = None,
    resource_id: str = "",
) -> Tuple[Dict[str, Dict], List[str]]:
    """Raw stats per header for every column; and the headers left without stats.

    Reads 25 columns per batch. A batch that times out is retried as batches
    of 5, then one column at a time, so only the columns that are really too
    slow lose their stats. Past ``deadline`` (a ``time.monotonic()`` value) the
    remaining columns are left without stats. Each timeout is logged.
    """
    stats: Dict[str, Dict] = {}
    unavailable: List[str] = []
    pending = [
        list(columns[i : i + STATS_BATCH_COLUMNS])
        for i in range(0, len(columns), STATS_BATCH_COLUMNS)
    ]
    while pending:
        batch = pending.pop(0)
        if deadline is not None and time.monotonic() >= deadline:
            logger.warning(
                "qe_profile_time_budget_used",
                resource_id=resource_id,
                columns_left=len(batch) + sum(map(len, pending)),
            )
            unavailable.extend(c.header for b in [batch, *pending] for c in b)
            break
        try:
            stats.update(_read_batch(table, batch))
        except QueryTooSlow:
            logger.warning(
                "qe_profile_batch_timed_out",
                resource_id=resource_id,
                columns=len(batch),
                timeout_ms=settings.QE_PROFILE_TIMEOUT_MS,
            )
            smaller = next((size for size in SPLIT_SIZES if size < len(batch)), None)
            if smaller is None:
                unavailable.extend(column.header for column in batch)
            else:
                pending[:0] = [batch[i : i + smaller] for i in range(0, len(batch), smaller)]
    return stats, unavailable


def _read_batch(table: str, batch: List[ColumnRef]) -> Dict[str, Dict]:
    aggregates = _read_aggregates(table, batch)
    for column in batch:
        found = aggregates[column.header]
        found["kind"] = detect_kind(
            column.storage_type,
            found["non_null"],
            found["placeholder_count"],
            found["numeric_like"],
        )
    numeric_text = [c for c in batch if aggregates[c.header]["kind"] == KIND_NUMERIC_TEXT]
    for header, ranges in _read_numeric_text_ranges(table, numeric_text).items():
        aggregates[header].update(ranges)
    values = _read_values(table, batch, aggregates)
    samples = _read_samples(
        table, [c for c in batch if aggregates[c.header]["distinct"] > VALUES_CAP]
    )
    for column in batch:
        found = aggregates[column.header]
        found["values"] = values.get(column.header, {}).get("values")
        found["odd_tokens"] = values.get(column.header, {}).get("odd_tokens", [])
        found["samples"] = samples.get(column.header, [])
    return aggregates


def _one_row(table: str, parts: List[pg_sql.Composable], params: List[Any]) -> Tuple[Any, ...]:
    query = with_row_limit(
        pg_sql.SQL("SELECT ")
        + pg_sql.SQL(", ").join(parts)
        + pg_sql.SQL(" FROM {}").format(pg_sql.Identifier(table)),
        1,
    )
    return run_read_only_query(
        query, params, timeout_ms=settings.QE_PROFILE_TIMEOUT_MS, max_rows=1
    ).rows[0]


def _read_aggregates(table: str, batch: List[ColumnRef]) -> Dict[str, Dict]:
    parts: List[pg_sql.Composable] = []
    params: List[Any] = []
    layout: List[Tuple[str, str]] = []

    def add(
        header: str, name: str, expression: pg_sql.Composable, extra: Sequence[Any] = ()
    ) -> None:
        parts.append(expression)
        params.extend(extra)
        layout.append((header, name))

    for column in batch:
        c = _column_ident(column.header)
        add(column.header, "non_null", pg_sql.SQL("count({})").format(c))
        add(column.header, "distinct", pg_sql.SQL("count(DISTINCT {})").format(c))
        if column.is_number or column.is_date:
            add(column.header, "min", pg_sql.SQL("min({})").format(c))
            add(column.header, "max", pg_sql.SQL("max({})").format(c))
        if column.is_number:
            add(column.header, "mean", pg_sql.SQL("avg({})").format(c))
        if column.is_text:
            add(
                column.header,
                "numeric_like",
                pg_sql.SQL("count(*) FILTER (WHERE {} ~ %s)").format(c),
                [NUMERIC_TEXT_RE],
            )
            add(
                column.header,
                "placeholder_count",
                pg_sql.SQL("count(*) FILTER (WHERE lower(btrim({})) = ANY(%s))").format(c),
                [PLACEHOLDERS],
            )

    row = _one_row(table, parts, params)
    found: Dict[str, Dict] = {
        column.header: {"numeric_like": 0, "placeholder_count": 0, "non_finite": False}
        for column in batch
    }
    for (header, name), value in zip(layout, row):
        number, non_finite = to_json_number(value)
        found[header][name] = number
        found[header]["non_finite"] |= non_finite
    return found


def _read_numeric_text_ranges(table: str, columns: List[ColumnRef]) -> Dict[str, Dict]:
    """Min, max and mean of numbers written as text, through the guarded cast (only those columns)."""
    if not columns:
        return {}
    parts: List[pg_sql.Composable] = []
    params: List[Any] = []
    for column in columns:
        cast, cast_params = numeric_text_cast(_column_ident(column.header))
        for function in ("min", "max", "avg"):
            parts.append(pg_sql.SQL(function + "({})").format(cast))
            params.extend(cast_params)
    row = _one_row(table, parts, params)
    ranges: Dict[str, Dict] = {}
    for position, column in enumerate(columns):
        values = [to_json_number(v)[0] for v in row[position * 3 : position * 3 + 3]]
        ranges[column.header] = dict(zip(("min", "max", "mean"), values))
    return ranges


def _read_values(
    table: str, batch: List[ColumnRef], aggregates: Dict[str, Dict]
) -> Dict[str, Dict[str, Any]]:
    parts: List[pg_sql.Composable] = []
    params: List[Any] = []
    max_rows = 0
    table_ident = pg_sql.Identifier(table)
    for position, column in enumerate(batch):
        c = _column_ident(column.header)
        found = aggregates[column.header]
        if found["distinct"] and found["distinct"] <= VALUES_CAP:
            parts.append(
                pg_sql.SQL(
                    "(SELECT {i} AS col, 'v' AS part, left({c}::text, {n}) AS value, count(*) AS hits "
                    "FROM {t} WHERE {c} IS NOT NULL GROUP BY 3 ORDER BY 4 DESC, 3 ASC LIMIT {cap})"
                ).format(
                    i=pg_sql.Literal(position),
                    c=c,
                    n=pg_sql.Literal(VALUE_CHARS),
                    t=table_ident,
                    cap=pg_sql.Literal(VALUES_CAP),
                )
            )
            max_rows += VALUES_CAP
        elif found["kind"] == KIND_NUMERIC_TEXT:
            parts.append(
                pg_sql.SQL(
                    "(SELECT {i} AS col, 'o' AS part, left({c}, {n}) AS value, count(*) AS hits "
                    "FROM {t} WHERE {c} IS NOT NULL AND NOT ({c} ~ %s) "
                    "GROUP BY 3 ORDER BY 4 DESC, 3 ASC LIMIT {cap})"
                ).format(
                    i=pg_sql.Literal(position),
                    c=c,
                    n=pg_sql.Literal(VALUE_CHARS),
                    t=table_ident,
                    cap=pg_sql.Literal(ODD_TOKENS),
                )
            )
            params.append(NUMERIC_TEXT_RE)
            max_rows += ODD_TOKENS
    if not parts:
        return {}
    # Wrapped, because one parenthesised SELECT may not take a second LIMIT.
    query = with_row_limit(
        pg_sql.SQL("SELECT * FROM (")
        + pg_sql.SQL(" UNION ALL ").join(parts)
        + pg_sql.SQL(") AS qe_values"),
        max_rows,
    )
    rows = run_read_only_query(
        query, params, timeout_ms=settings.QE_PROFILE_TIMEOUT_MS, max_rows=max_rows
    ).rows

    found_values: Dict[str, Dict[str, Any]] = {}
    for position, part, value, hits in rows:
        header = batch[position].header
        entry = found_values.setdefault(header, {})
        key = "values" if part == "v" else "odd_tokens"
        entry.setdefault(key, []).append([value, int(hits)])
    return found_values


def _read_samples(table: str, batch: List[ColumnRef]) -> Dict[str, List[str]]:
    if not batch:
        return {}
    columns = pg_sql.SQL(", ").join(
        pg_sql.SQL("left({}::text, {})").format(
            _column_ident(c.header), pg_sql.Literal(VALUE_CHARS)
        )
        for c in batch
    )
    query = with_row_limit(
        pg_sql.SQL("SELECT {} FROM {}").format(columns, pg_sql.Identifier(table)), SAMPLE_ROWS
    )
    rows = run_read_only_query(
        query, [], timeout_ms=settings.QE_PROFILE_TIMEOUT_MS, max_rows=SAMPLE_ROWS
    ).rows
    samples: Dict[str, List[str]] = {}
    for position, column in enumerate(batch):
        seen: List[str] = []
        for row in rows:
            value = row[position]
            if value is not None and value not in seen:
                seen.append(value)
        samples[column.header] = seen
    return samples


def odd_tokens_from_values(values: Optional[List[List[Any]]]) -> List[str]:
    """The most common non-numeric tokens among a numeric-text column's values (≤ 5)."""
    odd = [value for value, _ in values or [] if not _NUMERIC_TEXT.match(str(value))]
    return odd[:ODD_TOKENS]
