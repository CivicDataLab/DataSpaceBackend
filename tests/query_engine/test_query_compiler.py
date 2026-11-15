"""Layer 2: the SQL the compiler builds (Q3), rendered without a database."""

from typing import Any, Dict, List

from psycopg2 import sql as pg_sql

from api.services.query_engine.column_stats import NUMERIC_TEXT_RE, NUMERIC_TEXT_STRIP_RE
from api.services.query_engine.query_compiler import compile_query
from api.services.query_engine.query_spec import validate_query_spec
from tests.query_engine.query_fixtures import health_stats, wide_stats

TABLE = "rdt_0123456789abcdef0123456789abcdef"


def render(part: Any) -> str:
    if isinstance(part, pg_sql.Composed):
        return "".join(render(p) for p in part.seq)
    if isinstance(part, pg_sql.SQL):
        return part.string
    if isinstance(part, pg_sql.Identifier):
        return ".".join('"' + s.replace('"', '""') + '"' for s in part.strings)
    if isinstance(part, pg_sql.Literal):
        return repr(part.wrapped)
    raise AssertionError(f"unexpected part {part!r}")


def compiled(data: Dict[str, Any], stats: Dict[str, Any] = None) -> Any:
    stats = stats or health_stats()
    return compile_query(validate_query_spec({"scope": "platform", **data}, stats), stats, TABLE)


def test_a_plain_aggregate() -> None:
    query = compiled(
        {"group_by": ["District"], "measures": [{"fn": "avg", "column": "IMR (%)", "as": "imr"}]}
    )
    assert render(query.sql) == (
        'SELECT "g0", "imr" FROM (SELECT "District" AS "g0", avg("IMR (%%)") AS "imr" '
        f'FROM "{TABLE}" WHERE ("District" IS NULL OR "District"::text <> ALL(%s)) '
        'GROUP BY "District") AS q ORDER BY "g0" ASC NULLS LAST LIMIT 51'
    )
    assert query.params == [["Total"]]
    assert query.output_columns == ["District", "imr"]


def test_long_compare_computes_change_and_percent_change_in_sql() -> None:
    query = compiled(
        {
            "group_by": ["District"],
            "measures": [{"fn": "avg", "column": "Stunting (%)", "as": "stunting"}],
            "compare": {"column": "Survey round", "base": "2015-16", "target": "2019-20"},
            "order_by": [{"by": "stunting__change", "dir": "asc"}],
            "limit": 20,
        }
    )
    text = render(query.sql)
    assert 'avg("Stunting (%%)") FILTER (WHERE "Survey round" = %s) AS "stunting__base"' in text
    assert '("stunting__target" - "stunting__base") AS "stunting__change"' in text
    assert (
        '100.0 * ("stunting__target" - "stunting__base") / NULLIF("stunting__base", 0) '
        'AS "stunting__pct_change"' in text
    )
    assert text.endswith('ORDER BY "stunting__change" ASC NULLS LAST, "g0" ASC NULLS LAST LIMIT 21')
    assert query.params == ["2015-16", "2019-20", ["Total"], ["2015-16", "2019-20"]]


def test_numbers_stored_as_text_use_the_guarded_cast_with_regexes_as_params() -> None:
    query = compiled(
        {
            "filters": [{"column": "Population", "op": "gt", "value": 100000}],
            "measures": [{"fn": "sum", "column": "Population", "as": "people"}],
        }
    )
    text = render(query.sql)
    assert text.startswith(
        "WITH qe_patterns AS (SELECT %s::text AS qe_numeric_re, %s::text AS qe_strip_re) "
    )
    assert query.params[:2] == [NUMERIC_TEXT_RE, NUMERIC_TEXT_STRIP_RE]
    assert NUMERIC_TEXT_RE not in text and "[,%" not in text
    assert 'sum((CASE WHEN "Population" ~ (SELECT qe_numeric_re FROM qe_patterns)' in text
    assert '"__ignored_people"' in text
    assert query.ignored_aliases == {"__ignored_people": "people"}


def test_values_are_never_in_the_sql_text() -> None:
    query = compiled(
        {
            "filters": [
                {"column": "District", "op": "in", "value": ["Kamrup", "O'Brien; DROP"]},
                {"column": "Remarks", "op": "icontains", "value": "go"},
                {"column": "Year", "op": "eq", "value": 2019},
            ],
            "measures": [{"fn": "count", "as": "n"}],
        }
    )
    text = render(query.sql)
    for value in ("Kamrup", "O'Brien", "2019", "go"):
        assert value not in text
    assert isinstance(query.params, list)
    assert ["Kamrup", "O'Brien; DROP"] in query.params


def test_share_of_total_and_median() -> None:
    query = compiled(
        {
            "group_by": ["State"],
            "measures": [
                {"fn": "sum", "column": "IMR (%)", "as": "total"},
                {"fn": "median", "column": "IMR (%)", "as": "mid"},
            ],
            "share_of_total": True,
        }
    )
    text = render(query.sql)
    assert '100.0 * "total" / NULLIF(SUM("total") OVER (), 0) AS "total__share_pct"' in text
    assert 'percentile_cont(0.5) WITHIN GROUP (ORDER BY "IMR (%%)") AS "mid"' in text
    assert query.output_columns == ["State", "total", "total__share_pct", "mid"]


def test_wide_compare_reads_the_two_year_columns() -> None:
    query = compiled(
        {
            "group_by": ["District"],
            "measures": [{"fn": "sum", "as": "value"}],
            "compare": {"base_column": "2015-16", "target_column": "2019-20"},
        },
        wide_stats(),
    )
    text = render(query.sql)
    assert 'sum("2015-16") AS "value__base"' in text
    assert 'sum("2019-20") AS "value__target"' in text


def test_total_rows_kept_when_asked() -> None:
    query = compiled({"measures": [{"fn": "count", "as": "n"}], "include_total_rows": True})
    assert "<> ALL" not in render(query.sql)
    assert query.params == []


def test_rows_mode_projects_and_limits() -> None:
    query = compiled({"mode": "rows", "columns": ["District", "IMR (%)"], "limit": 5})
    assert render(query.sql) == (
        f'SELECT "District" AS "c0", "IMR (%%)" AS "c1" FROM "{TABLE}" '
        'WHERE ("District" IS NULL OR "District"::text <> ALL(%s)) '
        'ORDER BY "c0" ASC NULLS LAST LIMIT 6'
    )


def test_every_statement_ends_with_its_row_limit() -> None:
    specs: List[Dict[str, Any]] = [
        {"measures": [{"fn": "count", "as": "n"}]},
        {"group_by": ["District"], "measures": [{"fn": "count", "as": "n"}], "limit": 7},
        {"mode": "rows", "limit": 3},
    ]
    for data in specs:
        query = compiled(data)
        assert render(query.sql).endswith(f"LIMIT {query.max_rows + 1}")
