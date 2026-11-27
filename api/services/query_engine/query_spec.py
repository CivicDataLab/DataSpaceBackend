"""Checking an analysis request ("query spec") against a table's profile.

The query engine never sends SQL. It sends a small structured request — which
rows (filters), grouped how, which numbers (count, count_distinct, sum, avg,
min, max, median), optionally comparing two years (long tables: two values of a
column; wide tables: two year columns) or adding each group's share of the
total — and ``validate_query_spec`` turns it into a ``QuerySpec`` or refuses it
with a 400 that names the valid choices.

What it guarantees for the compiler:
- every column is one of this table's profiled columns, matched exactly by its
  full header (so an injection-looking name is just an unknown column);
- every value is a scalar of the column's type (text compared as text, numbers
  as numbers; numeric-looking text compared through its guarded cast);
- no unknown keys anywhere (a ``scope`` nested in the spec is refused);
- caps: ≤ 10 filters, IN ≤ 100 values, strings ≤ 200 characters, ≤ 3 group-by
  columns, ≤ 5 numbers, ≤ 20 output columns, ≤ 3 sort keys; limits over their
  maximum are lowered (and said so in ``notes``), anything else over a cap is refused;
- one filter per (column, operator): two "not equal" filters on one column are
  refused with a pointer to ``nin`` (the filter builder keys by column and operator).

Pure: no database, no settings beyond the row cap.

Docs: api/views/query_engine/architecture.md
"""

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

from django.conf import settings

from api.services.query_engine.column_roles import KIND_DATE, KIND_NUMERIC_TEXT, NUMBER_KINDS
from api.services.query_engine.errors import BadRequest
from api.utils.data_indexing import _FILTER_OPERATORS

AGGREGATE = "aggregate"
ROWS = "rows"
FUNCTIONS = ("count", "count_distinct", "sum", "avg", "min", "max", "median")
NUMBER_FUNCTIONS = ("sum", "avg", "median")
RANGE_FUNCTIONS = ("min", "max")
SHARE_FUNCTIONS = ("count", "count_distinct", "sum")
COMPARE_SUFFIXES = ("base", "target", "change", "pct_change")
SHARE_SUFFIX = "share_pct"

COMPARISON_OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "in", "nin", "isnull", "notnull")
# Every operator the shared WHERE builder knows (text columns may use them all).
TEXT_OPS = tuple(_FILTER_OPERATORS)
BOOLEAN_OPS = ("eq", "ne", "isnull", "notnull")
LIST_OPS = ("in", "nin")
NULL_OPS = ("isnull", "notnull")

MAX_FILTERS = 10
MAX_IN_VALUES = 100
MAX_VALUE_CHARS = 200
MAX_GROUP_BY = 3
MAX_MEASURES = 5
MAX_OUTPUT_COLUMNS = 20
MAX_ORDER_BY = 3
AGGREGATE_DEFAULT_LIMIT = 50
ROWS_DEFAULT_LIMIT = 10
ROWS_MAX_LIMIT = 50
MAX_NAMES_IN_MESSAGE = 30

ALIAS_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
TOP_KEYS = {
    "scope",
    "mode",
    "filters",
    "group_by",
    "measures",
    "compare",
    "share_of_total",
    "include_total_rows",
    "order_by",
    "limit",
    "columns",
}
FILTER_KEYS = {"column", "op", "value"}
MEASURE_KEYS = {"fn", "column", "as"}
LONG_COMPARE_KEYS = {"column", "base", "target"}
WIDE_COMPARE_KEYS = {"base_column", "target_column"}
ORDER_KEYS = {"by", "dir"}


class SpecError(BadRequest):
    code = "bad_query_spec"


@dataclass(frozen=True)
class Filter:
    column: str
    op: str
    value: Any
    numeric_cast: bool = False


@dataclass(frozen=True)
class Measure:
    fn: str
    column: Optional[str]
    alias: str


@dataclass(frozen=True)
class Compare:
    column: Optional[str] = None
    base: Any = None
    target: Any = None
    base_column: Optional[str] = None
    target_column: Optional[str] = None

    @property
    def wide(self) -> bool:
        return self.base_column is not None


@dataclass(frozen=True)
class OrderBy:
    by: str
    dir: str


@dataclass(frozen=True)
class QuerySpec:
    mode: str
    filters: Tuple[Filter, ...]
    group_by: Tuple[str, ...]
    measures: Tuple[Measure, ...]
    compare: Optional[Compare]
    share_of_total: bool
    include_total_rows: bool
    order_by: Tuple[OrderBy, ...]
    limit: int
    columns: Tuple[str, ...]
    notes: Tuple[str, ...] = field(default=())

    def normalised(self) -> Dict[str, Any]:
        """The spec as it will run (defaults filled, limits clamped), for the response."""
        spec: Dict[str, Any] = {
            "mode": self.mode,
            "filters": [
                {"column": f.column, "op": f.op, "value": _plain(f.value)} for f in self.filters
            ],
            "include_total_rows": self.include_total_rows,
            "order_by": [asdict(o) for o in self.order_by],
            "limit": self.limit,
        }
        if self.mode == ROWS:
            spec["columns"] = list(self.columns)
            return spec
        spec["group_by"] = list(self.group_by)
        spec["measures"] = [{"fn": m.fn, "column": m.column, "as": m.alias} for m in self.measures]
        spec["share_of_total"] = self.share_of_total
        if self.compare is not None:
            spec["compare"] = (
                {
                    "base_column": self.compare.base_column,
                    "target_column": self.compare.target_column,
                }
                if self.compare.wide
                else {
                    "column": self.compare.column,
                    "base": _plain(self.compare.base),
                    "target": _plain(self.compare.target),
                }
            )
        return spec


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _names(names: Sequence[str]) -> str:
    shown = list(names)[:MAX_NAMES_IN_MESSAGE]
    more = len(names) - len(shown)
    return ", ".join(shown) + (f" (and {more} more)" if more > 0 else "")


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(message, reason="invalid_spec")


def _object(value: Any, where: str, allowed: set) -> Dict[str, Any]:
    _need(isinstance(value, dict), f"{where} must be an object.")
    unknown = sorted(set(value) - allowed)
    _need(not unknown, f"{where} has unknown keys; allowed: {', '.join(sorted(allowed))}.")
    return dict(value)


def _list(value: Any, where: str, cap: int) -> List[Any]:
    if value is None:
        return []
    _need(isinstance(value, list), f"{where} must be a list.")
    _need(len(value) <= cap, f"{where} allows at most {cap} entries.")
    return list(value)


class _Columns:
    """The table's columns as the profile describes them, by full header."""

    def __init__(self, stats: Dict[str, Any]) -> None:
        self.by_name = {c["name"]: c for c in stats.get("columns", [])}
        self.usable = [
            c["name"] for c in stats.get("columns", []) if c.get("available") and c.get("profiled")
        ]

    def get(self, name: Any, where: str) -> Dict[str, Any]:
        _need(isinstance(name, str), f"{where} must be a column name.")
        column = self.by_name.get(name)
        if column is not None and not column.get("available"):
            raise SpecError(f"{where} is not in the data table.", reason="column_unavailable")
        if column is not None and not column.get("profiled"):
            raise SpecError(
                f"{where} is not profiled (only the first 300 columns are) and can't be queried.",
                reason="column_not_profiled",
            )
        if column is None:
            raise SpecError(
                f"{where} is not a column of this table; columns: {_names(self.usable)}.",
                reason="unknown_column",
            )
        return dict(column)


def validate_query_spec(data: Any, stats: Dict[str, Any]) -> QuerySpec:
    """The checked, normalised spec for this table, or SpecError (400) saying what to change."""
    body = _object(data, "The query spec", TOP_KEYS)
    columns = _Columns(stats)
    mode = body.get("mode", AGGREGATE)
    _need(mode in (AGGREGATE, ROWS), "mode must be 'aggregate' or 'rows'.")
    notes: List[str] = []

    filters = _filters(body.get("filters"), columns)
    include_total_rows = _flag(body.get("include_total_rows"), "include_total_rows")

    if mode == ROWS:
        for key in ("group_by", "measures", "compare", "share_of_total"):
            _need(not body.get(key), f"{key} is only for mode 'aggregate'.")
        projected = _projected(body.get("columns"), columns)
        order_by = _order_by(body.get("order_by"), list(projected))
        limit = _limit(body.get("limit"), ROWS_DEFAULT_LIMIT, ROWS_MAX_LIMIT, notes)
        return QuerySpec(
            mode,
            filters,
            (),
            (),
            None,
            False,
            include_total_rows,
            order_by,
            limit,
            projected,
            tuple(notes),
        )

    _need(body.get("columns") is None, "columns is only for mode 'rows'; use group_by.")
    group_by = _group_by(body.get("group_by"), columns)
    compare = _compare(body.get("compare"), columns, group_by, stats)
    measures = _measures(body.get("measures"), columns, compare)
    share = _flag(body.get("share_of_total"), "share_of_total")
    if share:
        _need(compare is None, "share_of_total can't be combined with compare.")
        _need(bool(group_by), "share_of_total needs group_by.")
        _need(
            any(m.fn in SHARE_FUNCTIONS for m in measures),
            f"share_of_total needs a measure using one of: {', '.join(SHARE_FUNCTIONS)}.",
        )
    outputs = output_names(group_by, measures, compare, share)
    _need(
        len(outputs) <= MAX_OUTPUT_COLUMNS,
        f"The query would return {len(outputs)} columns; at most {MAX_OUTPUT_COLUMNS} are allowed.",
    )
    order_by = _order_by(body.get("order_by"), outputs)
    limit = _limit(
        body.get("limit"), AGGREGATE_DEFAULT_LIMIT, int(settings.QE_QUERY_MAX_ROWS), notes
    )
    return QuerySpec(
        mode,
        filters,
        group_by,
        measures,
        compare,
        share,
        include_total_rows,
        order_by,
        limit,
        (),
        tuple(notes),
    )


def output_names(
    group_by: Sequence[str],
    measures: Sequence[Measure],
    compare: Optional[Compare],
    share: bool,
) -> List[str]:
    """The result's column names in order: group columns, then each number's outputs."""
    names = list(group_by)
    for measure in measures:
        if compare is not None:
            names.extend(f"{measure.alias}__{suffix}" for suffix in COMPARE_SUFFIXES)
        else:
            names.append(measure.alias)
            if share and measure.fn in SHARE_FUNCTIONS:
                names.append(f"{measure.alias}__{SHARE_SUFFIX}")
    return names


def _flag(value: Any, where: str) -> bool:
    if value is None:
        return False
    _need(isinstance(value, bool), f"{where} must be true or false.")
    return bool(value)


def _filters(raw: Any, columns: _Columns) -> Tuple[Filter, ...]:
    found: List[Filter] = []
    seen: Dict[Tuple[str, str], int] = {}
    for index, item in enumerate(_list(raw, "filters", MAX_FILTERS)):
        where = f"filters[{index}]"
        item = _object(item, where, FILTER_KEYS)
        column = columns.get(item.get("column"), f"{where}.column")
        op = item.get("op", "eq")
        allowed = _ops_for(column)
        _need(op in allowed, f"{where}.op must be one of: {', '.join(allowed)}.")
        key = (column["name"], op)
        if key in seen:
            hint = "nin" if op == "ne" else "in" if op == "eq" else "one filter"
            raise SpecError(
                f"{where} repeats filters[{seen[key]}]'s column and operator; use {hint} instead.",
                reason="repeated_filter",
            )
        seen[key] = index
        value = _filter_value(column, op, item.get("value"), f"{where}.value")
        found.append(
            Filter(column["name"], op, value, numeric_cast=column.get("kind") == KIND_NUMERIC_TEXT)
        )
    return tuple(found)


def _ops_for(column: Dict[str, Any]) -> Tuple[str, ...]:
    kind = column.get("kind")
    if kind == "boolean":
        return BOOLEAN_OPS
    if kind in NUMBER_KINDS or kind == KIND_DATE:
        return COMPARISON_OPS
    return TEXT_OPS


def _filter_value(column: Dict[str, Any], op: str, value: Any, where: str) -> Any:
    if op in NULL_OPS:
        _need(value is None or isinstance(value, bool), f"{where} must be true, false or left out.")
        return True if value is None else value
    if op in LIST_OPS:
        _need(
            isinstance(value, list) and bool(value), f"{where} must be a non-empty list for '{op}'."
        )
        _need(len(value) <= MAX_IN_VALUES, f"{where} allows at most {MAX_IN_VALUES} values.")
        return [coerce_value(column, v, f"{where}[{i}]") for i, v in enumerate(value)]
    return coerce_value(column, value, where)


def coerce_value(column: Dict[str, Any], value: Any, where: str) -> Any:
    """A scalar from the spec as the column's type: text as text, numbers as numbers, dates as ISO text."""
    _need(
        isinstance(value, (str, int, float))
        and not isinstance(value, bool)
        or (column.get("kind") == "boolean" and isinstance(value, bool)),
        f"{where} must be a single text or number value.",
    )
    if isinstance(value, str):
        _need(
            len(value) <= MAX_VALUE_CHARS, f"{where} allows at most {MAX_VALUE_CHARS} characters."
        )
    kind = column.get("kind")
    storage = column.get("storage_type", "text")
    if kind == "boolean":
        _need(isinstance(value, bool), f"{where} must be true or false.")
        return value
    if kind == KIND_NUMERIC_TEXT or (kind in NUMBER_KINDS and storage != "bigint"):
        return _number(value, where)
    if kind in NUMBER_KINDS:
        number = _number(value, where)
        _need(number == number.to_integral_value(), f"{where} must be a whole number.")
        return int(number)
    if kind == KIND_DATE:
        try:
            # A real date, so the database compares it with the column's dates.
            return datetime.fromisoformat(str(value))
        except ValueError:
            raise SpecError(f"{where} must be a date like 2019-04-01.", reason="bad_value")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _number(value: Any, where: str) -> Decimal:
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        raise SpecError(f"{where} must be a number.", reason="bad_value")
    _need(number.is_finite(), f"{where} must be a number.")
    return number


def _group_by(raw: Any, columns: _Columns) -> Tuple[str, ...]:
    names: List[str] = []
    for index, name in enumerate(_list(raw, "group_by", MAX_GROUP_BY)):
        column = columns.get(name, f"group_by[{index}]")
        _need(column["name"] not in names, f"group_by[{index}] repeats a column.")
        names.append(column["name"])
    return tuple(names)


def _compare(
    raw: Any, columns: _Columns, group_by: Tuple[str, ...], stats: Dict[str, Any]
) -> Optional[Compare]:
    if raw is None:
        return None
    _need(isinstance(raw, dict), "compare must be an object.")
    if "base_column" in raw or "target_column" in raw:
        raw = _object(raw, "compare", WIDE_COMPARE_KEYS)
        _need(
            stats.get("layout") == "wide_years",
            "compare with base_column/target_column needs a table with one column per year; "
            "this table is long: use compare.column with base and target values.",
        )
        base = columns.get(raw.get("base_column"), "compare.base_column")
        target = columns.get(raw.get("target_column"), "compare.target_column")
        for column, where in ((base, "compare.base_column"), (target, "compare.target_column")):
            _need(column.get("kind") in NUMBER_KINDS, f"{where} must be a number column.")
        _need(base["name"] != target["name"], "compare needs two different year columns.")
        return Compare(base_column=base["name"], target_column=target["name"])
    raw = _object(raw, "compare", LONG_COMPARE_KEYS)
    column = columns.get(raw.get("column"), "compare.column")
    _need(column["name"] not in group_by, "compare.column can't also be in group_by.")
    base = coerce_value(column, raw.get("base"), "compare.base")
    target = coerce_value(column, raw.get("target"), "compare.target")
    _need(base != target, "compare.base and compare.target must differ.")
    return Compare(column=column["name"], base=base, target=target)


def _measures(raw: Any, columns: _Columns, compare: Optional[Compare]) -> Tuple[Measure, ...]:
    items = _list(raw, "measures", MAX_MEASURES)
    _need(bool(items), 'measures needs at least one entry, e.g. {"fn": "count"}.')
    found: List[Measure] = []
    for index, item in enumerate(items):
        where = f"measures[{index}]"
        item = _object(item, where, MEASURE_KEYS)
        fn = item.get("fn")
        _need(fn in FUNCTIONS, f"{where}.fn must be one of: {', '.join(FUNCTIONS)}.")
        column_name: Optional[str] = None
        if compare is not None and compare.wide:
            _need(
                item.get("column") is None,
                f"{where}.column must be left out: a wide compare reads the two year columns.",
            )
        elif item.get("column") is not None:
            column = columns.get(item["column"], f"{where}.column")
            if fn in NUMBER_FUNCTIONS:
                _need(column.get("kind") in NUMBER_KINDS, f"{where}: {fn} needs a number column.")
            if fn in RANGE_FUNCTIONS:
                _need(
                    column.get("kind") in NUMBER_KINDS + (KIND_DATE,),
                    f"{where}: {fn} needs a number or date column.",
                )
            column_name = column["name"]
        else:
            _need(fn == "count", f"{where}.column is needed for {fn}.")
        alias = item.get("as") or _default_alias(fn, index, found)
        _need(
            isinstance(alias, str) and bool(ALIAS_RE.match(alias)) and "__" not in alias,
            f"{where}.as must be lower-case letters, digits and single underscores, "
            "starting with a letter (at most 41 characters).",
        )
        _need(alias not in {m.alias for m in found}, f"{where}.as repeats another measure's name.")
        found.append(Measure(fn=fn, column=column_name, alias=alias))
    return tuple(found)


def _default_alias(fn: str, index: int, found: Sequence[Measure]) -> str:
    taken = {m.alias for m in found}
    return fn if fn not in taken else f"{fn}_{index + 1}"


def _projected(raw: Any, columns: _Columns) -> Tuple[str, ...]:
    if raw is None:
        return tuple(columns.usable[:MAX_OUTPUT_COLUMNS])
    names: List[str] = []
    for index, name in enumerate(_list(raw, "columns", MAX_OUTPUT_COLUMNS)):
        column = columns.get(name, f"columns[{index}]")
        _need(column["name"] not in names, f"columns[{index}] repeats a column.")
        names.append(column["name"])
    _need(bool(names), "columns needs at least one column.")
    return tuple(names)


def _order_by(raw: Any, outputs: Sequence[str]) -> Tuple[OrderBy, ...]:
    found: List[OrderBy] = []
    for index, item in enumerate(_list(raw, "order_by", MAX_ORDER_BY)):
        where = f"order_by[{index}]"
        item = _object(item, where, ORDER_KEYS)
        by = item.get("by")
        _need(by in outputs, f"{where}.by must be one of the result's columns: {_names(outputs)}.")
        direction = item.get("dir", "asc")
        _need(direction in ("asc", "desc"), f"{where}.dir must be 'asc' or 'desc'.")
        found.append(OrderBy(by=by, dir=direction))
    return tuple(found)


def _limit(raw: Any, default: int, maximum: int, notes: List[str]) -> int:
    if raw is None:
        return default
    _need(
        isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1,
        "limit must be a whole number ≥ 1.",
    )
    if raw > maximum:
        notes.append(f"limit lowered from {raw} to {maximum}, the most one query returns")
        return maximum
    return int(raw)
