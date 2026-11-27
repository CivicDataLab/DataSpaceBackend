"""Layer 1 (real Postgres data database): analysis queries on tables the producer built (C1–C10).

Each table comes from ``index_resource_data`` on a fixture CSV and is profiled
for real; the spec is checked, compiled and run through the read-only
executor, and the numbers are compared with ones worked out by hand.
"""

from typing import Any, Callable, Dict, List, Optional

import pytest

from api.models import Resource
from api.services.query_engine.data_reader import run_read_only_query
from api.services.query_engine.geography_match import GeographyIndex
from api.services.query_engine.profiles import build_resource_stats
from api.services.query_engine.query_compiler import compile_query
from api.services.query_engine.query_spec import validate_query_spec
from tests.data_index.support import uses_data_db

LONG_ENGLISH = "Percentage of children age 6-59 months who are anaemic (%) in the district"
HINDI = "जिले में एनीमिया से पीड़ित बच्चों का प्रतिशत"


class Table:
    """A profiled table and a way to run specs on it."""

    def __init__(self, resource: Resource, geography: GeographyIndex) -> None:
        self.resource = resource
        self.stats = build_resource_stats(resource, geography)

    def run(self, **spec: Any) -> Dict[str, Any]:
        checked = validate_query_spec({"scope": "platform", **spec}, self.stats)
        compiled = compile_query(checked, self.stats, self.resource.resourcedatatable.table_name)
        result = run_read_only_query(
            compiled.sql, compiled.params, timeout_ms=5000, max_rows=compiled.max_rows
        )
        visible = [i for i, a in enumerate(compiled.aliases) if a not in compiled.ignored_aliases]
        hidden = {a: i for i, a in enumerate(compiled.aliases) if a in compiled.ignored_aliases}
        rows = [[_plain(row[i]) for i in visible] for row in result.rows]
        ignored = {
            compiled.ignored_aliases[a]: int(result.rows[0][i] or 0) if result.rows else 0
            for a, i in hidden.items()
        }
        return {
            "columns": compiled.output_columns,
            "rows": rows,
            "truncated": result.truncated,
            "sql": result.sql,
            "ignored": ignored,
            "notes": compiled.notes,
        }


def _plain(value: Any) -> Any:
    try:
        return round(float(value), 6) if value is not None and not isinstance(value, str) else value
    except (TypeError, ValueError):
        return value


@pytest.fixture
def table(make_table_resource: Callable, geography: GeographyIndex) -> Callable[[str], Table]:
    return lambda csv: Table(make_table_resource(csv), geography)


def by_first(rows: List[List[Any]]) -> Dict[Any, List[Any]]:
    return {row[0]: row[1:] for row in rows}


@uses_data_db
def test_a_percent_column_works_everywhere(table: Callable) -> None:
    health = table("district_health.csv")

    grouped = health.run(
        filters=[{"column": "IMR (%)", "op": "gte", "value": 30}],
        group_by=["IMR (%)"],
        measures=[{"fn": "avg", "column": "IMR (%)", "as": "imr"}, {"fn": "count", "as": "n"}],
        order_by=[{"by": "IMR (%)", "dir": "desc"}],
        limit=3,
    )
    plain = health.run(measures=[{"fn": "max", "column": "IMR (%)", "as": "top"}])

    assert grouped["rows"] == [[40.0, 40.0, 1], [38.0, 38.0, 1], [32.5, 32.5, 1]]
    assert '"IMR (%)"' in grouped["sql"]
    assert plain["rows"] == [[40.0]]


@uses_data_db
def test_quoted_multiline_duplicate_long_and_hindi_headers_are_addressed_by_full_header(
    table: Callable,
) -> None:
    odd = table("odd_headers.csv")
    names = [c["name"] for c in odd.stats["columns"]]
    assert all(c["available"] for c in odd.stats["columns"])
    first, second, dup, dup_again = names[:4]

    rows = odd.run(mode="rows", columns=names, order_by=[{"by": dup, "dir": "asc"}])
    grouped = odd.run(
        filters=[
            {"column": HINDI, "op": "gt", "value": 1.0},
            {"column": first, "op": "ne", "value": "x"},
        ],
        group_by=[first],
        measures=[
            {"fn": "avg", "column": LONG_ENGLISH, "as": "anaemia"},
            {"fn": "sum", "column": HINDI, "as": "hindi_total"},
            {"fn": "sum", "column": dup_again, "as": "dup_total"},
        ],
    )

    assert rows["columns"] == names
    assert rows["rows"][0][2:] == [1.0, 2.0, 45.5, 1.25]
    assert by_first(grouped["rows"]) == {"Kamrup": [42.75, 4.25, 8.0], "Nagaon": [50.0, 2.5, 4.0]}


@uses_data_db
def test_numbers_stored_as_text_sum_and_report_the_rows_ignored(table: Callable) -> None:
    counts = table("numeric_text.csv")

    result = counts.run(measures=[{"fn": "sum", "column": "Count", "as": "total"}])

    assert result["rows"] == [[123468.5]]
    assert result["ignored"] == {"total": 2}


@uses_data_db
def test_a_number_filter_on_a_text_year_column_matches_its_text(table: Callable) -> None:
    years = table("year_text.csv")
    assert next(c for c in years.stats["columns"] if c["name"] == "Year")["kind"] == "text"

    result = years.run(
        filters=[{"column": "Year", "op": "eq", "value": 2019}],
        measures=[{"fn": "sum", "column": "Cases", "as": "cases"}],
    )

    assert result["rows"] == [[12.0]]


@uses_data_db
def test_long_compare_matches_hand_computed_changes(table: Callable) -> None:
    rounds = table("compare.csv")

    result = rounds.run(
        group_by=["District"],
        measures=[{"fn": "avg", "column": "Stunting", "as": "stunting"}],
        compare={"column": "Round", "base": "2015-16", "target": "2019-20"},
        order_by=[{"by": "stunting__change", "dir": "asc"}],
    )

    assert result["columns"] == [
        "District",
        "stunting__base",
        "stunting__target",
        "stunting__change",
        "stunting__pct_change",
    ]
    assert result["rows"] == [
        ["Kamrup", 40.0, 34.0, -6.0, -15.0],
        ["Nagaon", 0.0, 10.0, 10.0, None],
        ["Dibrugarh", None, 20.0, None, None],
    ]


@uses_data_db
def test_wide_compare_matches_hand_computed_changes(table: Callable) -> None:
    wide = table("wide_years.csv")

    result = wide.run(
        group_by=["District"],
        measures=[{"fn": "sum", "as": "value"}],
        compare={"base_column": "2015-16", "target_column": "2019-20"},
    )

    assert by_first(result["rows"]) == {
        "Dibrugarh": [20.0, 22.0, 2.0, 10.0],
        "Kamrup": [10.0, 12.0, 2.0, 20.0],
    }


@uses_data_db
def test_shares_add_up_to_100_and_the_median_matches(table: Callable) -> None:
    health = table("district_health.csv")

    shares = health.run(
        group_by=["District"],
        measures=[{"fn": "sum", "column": "Stunting (%)", "as": "stunting"}],
        share_of_total=True,
    )
    median = health.run(measures=[{"fn": "median", "column": "IMR (%)", "as": "mid"}])

    assert by_first(shares["rows"])["Kamrup"][0] == 75.0
    assert abs(sum(row[2] for row in shares["rows"]) - 100.0) < 1e-6
    # IMR without the two Total rows: 22, 25, 30.5, 32.5, 38, 40.
    assert median["rows"] == [[31.5]]


@uses_data_db
def test_total_rows_are_left_out_unless_asked(table: Callable) -> None:
    health = table("district_health.csv")

    default = health.run(measures=[{"fn": "count", "as": "n"}])
    kept = health.run(measures=[{"fn": "count", "as": "n"}], include_total_rows=True)

    assert default["rows"] == [[6]]
    assert any("Total" in note for note in default["notes"])
    assert kept["rows"] == [[8]]


@uses_data_db
def test_a_long_in_list_a_numeric_text_cast_and_compare_keep_their_parameter_order(
    table: Callable,
) -> None:
    counts = table("numeric_text.csv")
    districts = ["Kamrup"] + [f"Nowhere {i}" for i in range(99)]

    result = counts.run(
        filters=[{"column": "District", "op": "in", "value": districts}],
        group_by=["District"],
        measures=[{"fn": "sum", "column": "Count", "as": "total"}],
        compare={"column": "Round", "base": "2015-16", "target": "2019-20"},
    )

    assert result["rows"] == [
        ["Kamrup", 123456.0, 12.5, -123443.5, pytest.approx(-99.989875, abs=1e-6)]
    ]


@uses_data_db
def test_limits_mark_truncation_in_both_modes(table: Callable) -> None:
    health = table("district_health.csv")

    rows = health.run(mode="rows", columns=["District", "IMR (%)"], limit=2)
    grouped = health.run(group_by=["District"], measures=[{"fn": "count", "as": "n"}], limit=1)

    assert len(rows["rows"]) == 2 and rows["truncated"] is True
    assert rows["sql"].endswith("LIMIT 3")
    assert grouped["rows"] == [["Dibrugarh", 2]] and grouped["truncated"] is True


@uses_data_db
def test_a_column_that_is_one_total_like_value_throughout_keeps_its_rows(table: Callable) -> None:
    national = table("national.csv")
    columns = {c["name"]: c for c in national.stats["columns"]}
    assert columns["Country"]["total_markers"] == ["India"]

    result = national.run(
        group_by=["Year"], measures=[{"fn": "sum", "column": "Emissions", "as": "total"}]
    )

    # Country = "India" on every row is not a total row; "All India" under State is.
    assert result["rows"] == [[2015, 100.0], [2020, 120.0]]
    assert not any("Country" in note for note in result["notes"])


@uses_data_db
def test_a_total_row_asked_for_by_name_is_kept(table: Callable) -> None:
    national = table("national.csv")

    result = national.run(
        filters=[{"column": "State", "op": "eq", "value": "All India"}],
        group_by=["Year"],
        measures=[{"fn": "sum", "column": "Emissions", "as": "total"}],
    )

    assert result["rows"] == [[2015, 100.0], [2020, 120.0]]


@uses_data_db
def test_long_headers_work_as_groups_and_filters(table: Callable) -> None:
    odd = table("odd_headers.csv")

    result = odd.run(
        filters=[{"column": LONG_ENGLISH, "op": "gte", "value": 45}],
        group_by=[LONG_ENGLISH],
        measures=[{"fn": "sum", "column": HINDI, "as": "hindi_total"}],
    )

    assert result["rows"] == [[45.5, 1.25], [50.0, 2.5]]


@uses_data_db
def test_real_date_columns_filter_and_compare(geography: GeographyIndex) -> None:
    from django.db import connections

    from tests.data_index.support import DATA_DB

    with connections[DATA_DB].cursor() as cursor:
        cursor.execute(
            'CREATE TABLE "qe_dates" ("On" timestamp, "Cases" bigint); '
            "INSERT INTO \"qe_dates\" VALUES ('2019-01-01', 5), ('2019-06-01', 7), ('2020-01-01', 9)"
        )
    stats = {
        "row_count": 3,
        "layout": "long",
        "analysable": True,
        "columns": [
            {
                "name": "On",
                "kind": "date",
                "role": "time_date",
                "storage_type": "timestamp without time zone",
                "available": True,
                "profiled": True,
            },
            {
                "name": "Cases",
                "kind": "numeric",
                "role": "measure",
                "storage_type": "bigint",
                "available": True,
                "profiled": True,
            },
        ],
    }

    def run(**spec: Any) -> List[Any]:
        checked = validate_query_spec({"scope": "platform", **spec}, stats)
        compiled = compile_query(checked, stats, "qe_dates")
        return run_read_only_query(
            compiled.sql, compiled.params, timeout_ms=5000, max_rows=compiled.max_rows
        ).rows

    assert run(
        filters=[{"column": "On", "op": "in", "value": ["2019-01-01", "2020-01-01"]}],
        measures=[{"fn": "sum", "column": "Cases", "as": "n"}],
    ) == [(14,)]
    assert (
        run(
            filters=[{"column": "On", "op": "gte", "value": "2019-06-01"}],
            measures=[{"fn": "max", "column": "On", "as": "latest"}],
        )[0][0].year
        == 2020
    )
    compared = run(
        measures=[{"fn": "sum", "column": "Cases", "as": "n"}],
        compare={"column": "On", "base": "2019-01-01", "target": "2020-01-01"},
    )
    assert [float(v) for v in compared[0][:3]] == [5.0, 9.0, 4.0]
