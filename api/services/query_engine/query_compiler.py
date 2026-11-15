"""Turning a checked query spec into one parameterised SELECT on a table's data table.

Pure: builds the statement, never runs it. Every number in the answer is
computed by the database — the change between two years, the percentage
change (``100 × (target − base) / NULLIF(base, 0)``, so a zero base gives
null), each group's share of the total, the median — never in Python.

Shape (aggregate mode)::

    [WITH qe_patterns AS (SELECT <numeric-text regex>, <strip regex>)]
    SELECT <groups>, <numbers>, <change / % change / share>, <hidden ignored counts>
    FROM (SELECT <group columns> AS g0.., <aggregates> FROM <table>
          WHERE <filters> AND <total rows left out> [AND <compare column> IN (base, target)]
          GROUP BY <group columns>) AS q
    ORDER BY <requested>, <groups> (nulls last)
    LIMIT <limit + 1>

Rows mode is ``SELECT <columns> FROM <table> WHERE … ORDER BY … LIMIT``.

- Columns are named by full header through ``_column_ident`` (doubles ``%``);
  results use short internal aliases (``g0``, ``c0``, the measure's ``as``) so
  Postgres's 63-byte cut never touches an output name; ``output_columns`` maps
  them back to headers.
- Numbers stored as text go through a guarded cast whose two regexes are
  parameters (in the ``qe_patterns`` CTE); each such measure also counts the
  rows it had to ignore.
- Filters reuse the data API's WHERE builder (``column_exprs`` for the casts).
- Rows whose value is a detected total marker ("Total", "All India") are left
  out unless ``include_total_rows``; a note says which. Not for a column that
  holds nothing but such a value (a "Country" column that is "India"
  throughout), and not for a label the request filters for by name.
- Every value is a parameter; the params list is always a list; the statement
  always ends with ``LIMIT limit + 1``.

Docs: api/views/query_engine/architecture.md
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from psycopg2 import sql as pg_sql  # type: ignore[import-untyped]

from api.services.query_engine.column_roles import KIND_NUMERIC_TEXT
from api.services.query_engine.column_stats import NUMERIC_TEXT_RE, NUMERIC_TEXT_STRIP_RE
from api.services.query_engine.data_reader import with_row_limit
from api.services.query_engine.query_spec import (
    AGGREGATE,
    NUMBER_FUNCTIONS,
    RANGE_FUNCTIONS,
    SHARE_FUNCTIONS,
    SHARE_SUFFIX,
    Measure,
    QuerySpec,
)
from api.utils.data_indexing import _build_where_clause, _column_ident

IGNORED_PREFIX = "__ignored_"


@dataclass(frozen=True)
class CompiledQuery:
    """A statement ready for the read-only executor, and how to read its result."""

    sql: pg_sql.Composed
    params: List[Any]
    aliases: List[str]
    output_columns: List[str]
    ignored_aliases: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    max_rows: int = 0


def _ident(alias: str) -> pg_sql.Identifier:
    return pg_sql.Identifier(alias)


def _cast(column: str) -> pg_sql.Composed:
    """The guarded numeric cast of a text column, reading its regexes from ``qe_patterns``."""
    return pg_sql.SQL(
        "(CASE WHEN {c} ~ (SELECT qe_numeric_re FROM qe_patterns) "
        "THEN regexp_replace({c}, (SELECT qe_strip_re FROM qe_patterns), '', 'g')::numeric END)"
    ).format(c=_column_ident(column))


class _Compiler:
    def __init__(self, spec: QuerySpec, stats: Dict[str, Any], table: str) -> None:
        self.spec = spec
        self.columns = {c["name"]: c for c in stats.get("columns", [])}
        self.table = pg_sql.Identifier(table)
        self.uses_patterns = False
        self.notes: List[str] = []

    def is_numeric_text(self, column: str) -> bool:
        return bool(self.columns.get(column, {}).get("kind") == KIND_NUMERIC_TEXT)

    def value_expr(self, column: str, for_numbers: bool) -> pg_sql.Composable:
        if for_numbers and self.is_numeric_text(column):
            self.uses_patterns = True
            return _cast(column)
        return _column_ident(column)

    def where(
        self, extra: Sequence[Tuple[pg_sql.Composable, List[Any]]]
    ) -> Tuple[pg_sql.Composable, List[Any]]:
        filters = {f"{f.column}__{f.op}": f.value for f in self.spec.filters}
        exprs = {
            f.column: self.value_expr(f.column, True) for f in self.spec.filters if f.numeric_cast
        }
        where_sql, params = _build_where_clause(
            filters, list(self.columns), column_exprs=exprs or None
        )
        clauses = [clause for clause, _ in extra]
        for _, clause_params in extra:
            params.extend(clause_params)
        if not clauses:
            return where_sql, params
        joined = pg_sql.SQL(" AND ").join(clauses)
        if filters:
            return pg_sql.Composed([where_sql, pg_sql.SQL(" AND "), joined]), params
        return pg_sql.Composed([pg_sql.SQL(" WHERE "), joined]), params

    def asked_values(self, column: str) -> List[str]:
        """Values the request names for a column with "eq" or "in" filters."""
        asked: List[str] = []
        for f in self.spec.filters:
            if f.column == column and f.op in ("eq", "in"):
                asked.extend(str(v) for v in (f.value if isinstance(f.value, list) else [f.value]))
        return asked

    def total_row_clauses(self) -> List[Tuple[pg_sql.Composable, List[Any]]]:
        if self.spec.include_total_rows:
            return []
        clauses = []
        for name, column in self.columns.items():
            markers = column.get("total_markers") or []
            if not (column.get("profiled") and markers):
                continue
            # A column that is nothing but a total-like value ("Country" = "India") has no
            # breakdown rows to protect: its rows are the data.
            if int(column.get("distinct") or 0) <= len(markers):
                continue
            # A total row the request asks for by name is kept.
            dropped = [m for m in markers if m not in self.asked_values(name)]
            if not dropped:
                continue
            clauses.append(
                (
                    pg_sql.SQL("({c} IS NULL OR {c}::text <> ALL(%s))").format(
                        c=_column_ident(name)
                    ),
                    [dropped],
                )
            )
            self.notes.append(f"rows where {name} is {', '.join(dropped)} left out (totals)")
        return clauses

    def aggregate(
        self, measure: Measure, column: Optional[str], side: Optional[Any]
    ) -> pg_sql.Composed:
        numbers = measure.fn in NUMBER_FUNCTIONS + RANGE_FUNCTIONS
        target = self.value_expr(column, numbers) if column else None
        if measure.fn == "count":
            call = (
                pg_sql.SQL("count({})").format(target)
                if target is not None
                else pg_sql.SQL("count(*)")
            )
        elif measure.fn == "count_distinct":
            call = pg_sql.SQL("count(DISTINCT {})").format(target)
        elif measure.fn == "median":
            call = pg_sql.SQL("percentile_cont(0.5) WITHIN GROUP (ORDER BY {})").format(target)
        else:
            call = pg_sql.SQL("{}({})").format(pg_sql.SQL(measure.fn), target)
        if side is None:
            return pg_sql.Composed([call])
        return pg_sql.Composed([call, pg_sql.SQL(" FILTER (WHERE "), side, pg_sql.SQL(")")])


def compile_query(spec: QuerySpec, stats: Dict[str, Any], table: str) -> CompiledQuery:
    """The statement, its params, and how to name its columns (see the module comment)."""
    compiler = _Compiler(spec, stats, table)
    if spec.mode == AGGREGATE:
        return _compile_aggregate(compiler)
    return _compile_rows(compiler)


def _with_patterns(
    compiler: _Compiler, body: pg_sql.Composable, params: List[Any]
) -> Tuple[pg_sql.Composable, List[Any]]:
    if not compiler.uses_patterns:
        return body, params
    prefix = pg_sql.SQL(
        "WITH qe_patterns AS (SELECT %s::text AS qe_numeric_re, %s::text AS qe_strip_re) "
    )
    return pg_sql.Composed([prefix, body]), [NUMERIC_TEXT_RE, NUMERIC_TEXT_STRIP_RE, *params]


def _order_clause(
    order: Sequence[Tuple[str, str]], tie_breakers: Sequence[str]
) -> pg_sql.Composable:
    keys = [(alias, direction) for alias, direction in order]
    keys += [(alias, "asc") for alias in tie_breakers if alias not in {a for a, _ in order}]
    if not keys:
        return pg_sql.SQL("")
    return pg_sql.SQL(" ORDER BY ") + pg_sql.SQL(", ").join(
        pg_sql.SQL("{} {} NULLS LAST").format(_ident(alias), pg_sql.SQL(direction.upper()))
        for alias, direction in keys
    )


def _compile_aggregate(compiler: _Compiler) -> CompiledQuery:
    spec = compiler.spec
    compare = spec.compare
    group_aliases = [f"g{i}" for i in range(len(spec.group_by))]
    inner: List[pg_sql.Composable] = [
        pg_sql.SQL("{} AS {}").format(_column_ident(column), _ident(alias))
        for column, alias in zip(spec.group_by, group_aliases)
    ]
    inner_params: List[Any] = []
    outer: List[pg_sql.Composable] = [_ident(alias) for alias in group_aliases]
    aliases = list(group_aliases)
    output = list(spec.group_by)
    ignored: Dict[str, str] = {}
    extra_where: List[Tuple[pg_sql.Composable, List[Any]]] = []

    if compare is not None and not compare.wide:
        # Only rows of the two compared values are read.
        compare_expr = compiler.value_expr(str(compare.column), True)
        extra_where.append(
            (pg_sql.SQL("{} = ANY(%s)").format(compare_expr), [[compare.base, compare.target]])
        )

    for measure in spec.measures:
        a = measure.alias
        if compare is None:
            inner.append(
                pg_sql.SQL("{} AS {}").format(
                    compiler.aggregate(measure, measure.column, None), _ident(a)
                )
            )
            outer.append(_ident(a))
            aliases.append(a)
            output.append(a)
            if spec.share_of_total and measure.fn in SHARE_FUNCTIONS:
                share = f"{a}__{SHARE_SUFFIX}"
                outer.append(
                    pg_sql.SQL("100.0 * {m} / NULLIF(SUM({m}) OVER (), 0) AS {s}").format(
                        m=_ident(a), s=_ident(share)
                    )
                )
                aliases.append(share)
                output.append(share)
        else:
            if compare.wide:
                base_sql = compiler.aggregate(measure, compare.base_column, None)
                target_sql = compiler.aggregate(measure, compare.target_column, None)
            else:
                side = pg_sql.SQL("{} = %s").format(compiler.value_expr(str(compare.column), True))
                base_sql = compiler.aggregate(measure, measure.column, side)
                target_sql = compiler.aggregate(measure, measure.column, side)
                # One placeholder in each FILTER, base first (the order they appear in the SQL).
                inner_params.extend([compare.base, compare.target])
            inner.append(pg_sql.SQL("{} AS {}").format(base_sql, _ident(f"{a}__base")))
            inner.append(pg_sql.SQL("{} AS {}").format(target_sql, _ident(f"{a}__target")))
            base, target = _ident(f"{a}__base"), _ident(f"{a}__target")
            outer.extend(
                [
                    base,
                    target,
                    pg_sql.SQL("({t} - {b}) AS {n}").format(
                        t=target, b=base, n=_ident(f"{a}__change")
                    ),
                    pg_sql.SQL("100.0 * ({t} - {b}) / NULLIF({b}, 0) AS {n}").format(
                        t=target, b=base, n=_ident(f"{a}__pct_change")
                    ),
                ]
            )
            for suffix in ("base", "target", "change", "pct_change"):
                aliases.append(f"{a}__{suffix}")
                output.append(f"{a}__{suffix}")

        counted = _ignored_column(compiler, measure)
        if counted is not None:
            hidden = f"{IGNORED_PREFIX}{a}"
            inner.append(
                pg_sql.SQL(
                    "sum(count(*) FILTER (WHERE {c} IS NOT NULL AND {cast} IS NULL)) OVER () AS {h}"
                ).format(
                    c=_column_ident(counted),
                    cast=compiler.value_expr(counted, True),
                    h=_ident(hidden),
                )
            )
            outer.append(_ident(hidden))
            aliases.append(hidden)
            ignored[hidden] = a

    where_sql, where_params = compiler.where(compiler.total_row_clauses() + extra_where)
    group_sql = (
        pg_sql.SQL(" GROUP BY ") + pg_sql.SQL(", ").join(_column_ident(c) for c in spec.group_by)
        if spec.group_by
        else pg_sql.SQL("")
    )
    inner_sql = pg_sql.Composed(
        [
            pg_sql.SQL("SELECT "),
            pg_sql.SQL(", ").join(inner),
            pg_sql.SQL(" FROM "),
            compiler.table,
            where_sql,
            group_sql,
        ]
    )
    order = [(_alias_for(o.by, spec.group_by, group_aliases), o.dir) for o in spec.order_by]
    body = pg_sql.Composed(
        [
            pg_sql.SQL("SELECT "),
            pg_sql.SQL(", ").join(outer),
            pg_sql.SQL(" FROM ("),
            inner_sql,
            pg_sql.SQL(") AS q"),
            _order_clause(order, group_aliases),
        ]
    )
    sql, params = _with_patterns(
        compiler, with_row_limit(body, spec.limit), inner_params + where_params
    )
    return CompiledQuery(
        sql=pg_sql.Composed([sql]),
        params=list(params),
        aliases=aliases,
        output_columns=output,
        ignored_aliases=ignored,
        notes=list(spec.notes) + compiler.notes,
        max_rows=spec.limit,
    )


def _ignored_column(compiler: _Compiler, measure: Measure) -> Optional[str]:
    """The numeric-text column whose unreadable rows this measure skips, if any."""
    if measure.fn not in NUMBER_FUNCTIONS + RANGE_FUNCTIONS:
        return None
    compare = compiler.spec.compare
    if compare is not None and compare.wide:
        return None
    if measure.column and compiler.is_numeric_text(measure.column):
        return measure.column
    return None


def _alias_for(name: str, group_by: Sequence[str], group_aliases: Sequence[str]) -> str:
    return group_aliases[list(group_by).index(name)] if name in group_by else name


def _compile_rows(compiler: _Compiler) -> CompiledQuery:
    spec = compiler.spec
    aliases = [f"c{i}" for i in range(len(spec.columns))]
    select = pg_sql.SQL(", ").join(
        pg_sql.SQL("{} AS {}").format(_column_ident(column), _ident(alias))
        for column, alias in zip(spec.columns, aliases)
    )
    where_sql, params = compiler.where(compiler.total_row_clauses())
    order = [(aliases[list(spec.columns).index(o.by)], o.dir) for o in spec.order_by]
    body = pg_sql.Composed(
        [
            pg_sql.SQL("SELECT "),
            select,
            pg_sql.SQL(" FROM "),
            compiler.table,
            where_sql,
            _order_clause(order, aliases[:1]),
        ]
    )
    sql, all_params = _with_patterns(compiler, with_row_limit(body, spec.limit), params)
    return CompiledQuery(
        sql=pg_sql.Composed([sql]),
        params=list(all_params),
        aliases=aliases,
        output_columns=list(spec.columns),
        notes=list(spec.notes) + compiler.notes,
        max_rows=spec.limit,
    )
