"""Layer 2: checking analysis requests against a profile (Q2)."""

from typing import Any, Dict

import pytest

from api.services.query_engine.query_spec import SpecError, validate_query_spec
from tests.query_engine.query_fixtures import health_stats, wide_stats


def spec(**fields: Any) -> Dict[str, Any]:
    return {
        "scope": "platform",
        "measures": [{"fn": "avg", "column": "IMR (%)", "as": "imr"}],
        **fields,
    }


def refused(data: Dict[str, Any], stats: Dict[str, Any] = None) -> str:
    with pytest.raises(SpecError) as raised:
        validate_query_spec(data, stats or health_stats())
    return raised.value.message


class TestAccepts:
    def test_the_plans_example(self) -> None:
        checked = validate_query_spec(
            {
                "scope": "collaborative:ab12cd34ef56",
                "mode": "aggregate",
                "filters": [{"column": "State", "op": "eq", "value": "Assam"}],
                "group_by": ["District"],
                "measures": [{"fn": "avg", "column": "Stunting (%)", "as": "stunting"}],
                "compare": {"column": "Survey round", "base": "2015-16", "target": "2019-20"},
                "share_of_total": False,
                "include_total_rows": False,
                "order_by": [{"by": "stunting__change", "dir": "asc"}],
                "limit": 20,
            },
            health_stats(),
        )
        assert checked.group_by == ("District",)
        assert checked.compare.base == "2015-16"
        assert checked.limit == 20

    def test_date_values_become_dates(self) -> None:
        from datetime import datetime

        stats = health_stats(
            columns=[
                {
                    "name": "On",
                    "kind": "date",
                    "role": "time_date",
                    "storage_type": "timestamp without time zone",
                    "available": True,
                    "profiled": True,
                }
            ]
        )
        checked = validate_query_spec(
            {
                "scope": "platform",
                "measures": [{"fn": "count"}],
                "filters": [{"column": "On", "op": "gte", "value": "2019-04-01"}],
            },
            stats,
        )
        assert checked.filters[0].value == datetime(2019, 4, 1)
        assert checked.normalised()["filters"][0]["value"] == "2019-04-01T00:00:00"

    def test_values_take_the_columns_type(self) -> None:
        checked = validate_query_spec(
            spec(
                filters=[
                    {"column": "Year", "op": "gte", "value": "2015"},
                    {"column": "Survey round", "op": "eq", "value": 2019},
                    {"column": "Population", "op": "gt", "value": "1,00,000"},
                ]
            ),
            health_stats(),
        )
        year, round_, population = checked.filters
        assert year.value == 2015
        assert round_.value == "2019"
        assert float(population.value) == 100000 and population.numeric_cast

    def test_over_cap_limits_are_lowered_and_say_so(self, settings: Any) -> None:
        settings.QE_QUERY_MAX_ROWS = 500
        checked = validate_query_spec(spec(limit=5000), health_stats())
        assert checked.limit == 500
        assert checked.normalised()["limit"] == 500
        assert any("lowered" in note for note in checked.notes)
        rows = validate_query_spec(
            {"scope": "platform", "mode": "rows", "limit": 999}, health_stats()
        )
        assert rows.limit == 50

    def test_gte_and_lte_on_one_column_are_fine(self) -> None:
        filters = [
            {"column": "Year", "op": "gte", "value": 2015},
            {"column": "Year", "op": "lte", "value": 2019},
        ]
        assert len(validate_query_spec(spec(filters=filters), health_stats()).filters) == 2

    def test_wide_compare_on_a_wide_table(self) -> None:
        checked = validate_query_spec(
            {
                "scope": "platform",
                "group_by": ["District"],
                "measures": [{"fn": "sum", "as": "value"}],
                "compare": {"base_column": "2015-16", "target_column": "2019-20"},
            },
            wide_stats(),
        )
        assert checked.compare.wide


class TestRefuses:
    def test_an_unknown_column_naming_the_valid_ones(self) -> None:
        message = refused(spec(group_by=["Districts"]))
        assert "District" in message and "IMR (%)" in message

    def test_an_injection_looking_name_is_just_an_unknown_column(self) -> None:
        message = refused(spec(group_by=['x"; DROP TABLE y; --']))
        assert "not a column" in message
        assert "DROP" not in message

    def test_a_column_beyond_the_profiled_300(self) -> None:
        assert "not profiled" in refused(spec(group_by=["c999"]))

    def test_a_column_missing_from_the_table(self) -> None:
        assert "not in the data table" in refused(spec(group_by=["Gone"]))

    def test_more_than_10_filters(self) -> None:
        filters = [{"column": "Year", "op": "ne", "value": y} for y in range(11)]
        assert "at most 10" in refused(spec(filters=filters))

    def test_more_than_100_in_values(self) -> None:
        filters = [{"column": "District", "op": "in", "value": [f"d{i}" for i in range(101)]}]
        assert "at most 100" in refused(spec(filters=filters))

    def test_a_value_over_200_characters(self) -> None:
        filters = [{"column": "District", "op": "eq", "value": "x" * 201}]
        assert "200 characters" in refused(spec(filters=filters))

    def test_more_than_3_group_by_columns(self) -> None:
        assert "at most 3" in refused(spec(group_by=["State", "District", "Year", "Remarks"]))

    def test_more_than_5_measures(self) -> None:
        measures = [{"fn": "count", "as": f"n{i}"} for i in range(6)]
        assert "at most 5" in refused(spec(measures=measures))

    def test_sum_on_plain_text(self) -> None:
        assert "number column" in refused(spec(measures=[{"fn": "sum", "column": "Remarks"}]))

    def test_the_compare_column_also_in_group_by(self) -> None:
        message = refused(
            spec(
                group_by=["Survey round"],
                compare={"column": "Survey round", "base": "2015-16", "target": "2019-20"},
            )
        )
        assert "can't also be in group_by" in message

    def test_a_wide_compare_on_a_long_table(self) -> None:
        message = refused(
            {
                "scope": "platform",
                "measures": [{"fn": "sum", "as": "v"}],
                "compare": {"base_column": "IMR (%)", "target_column": "Stunting (%)"},
            }
        )
        assert "this table is long" in message

    def test_ordering_by_an_unknown_name(self) -> None:
        message = refused(spec(order_by=[{"by": "nope"}]))
        assert "imr" in message

    @pytest.mark.parametrize("alias", ["Imr", "1x", "a__b", "x" * 42, "with space"])
    def test_a_bad_alias(self, alias: str) -> None:
        assert ".as must be" in refused(spec(measures=[{"fn": "count", "as": alias}]))

    def test_more_than_20_columns_in_rows_mode(self) -> None:
        stats = health_stats(
            columns=[
                {
                    "name": f"c{i}",
                    "kind": "numeric",
                    "role": "measure",
                    "storage_type": "bigint",
                    "available": True,
                    "profiled": True,
                }
                for i in range(21)
            ]
        )
        assert "at most 20" in refused(
            {"scope": "platform", "mode": "rows", "columns": [f"c{i}" for i in range(21)]}, stats
        )

    def test_measures_in_rows_mode(self) -> None:
        assert "only for mode 'aggregate'" in refused(spec(mode="rows"))

    def test_an_unknown_operator(self) -> None:
        filters = [{"column": "District", "op": "like", "value": "K%"}]
        assert "op must be one of" in refused(spec(filters=filters))

    def test_two_not_equal_filters_on_one_column_point_to_nin(self) -> None:
        filters = [
            {"column": "District", "op": "ne", "value": "Total"},
            {"column": "District", "op": "ne", "value": "Kamrup"},
        ]
        assert "use nin" in refused(spec(filters=filters))

    def test_a_scope_nested_in_the_spec(self) -> None:
        filters = [{"column": "District", "op": "eq", "value": "Kamrup", "scope": "platform"}]
        assert "unknown keys" in refused(spec(filters=filters))
        assert "unknown keys" in refused(
            spec(measures=[{"fn": "count", "as": "n", "scope": "collaborative:ab12cd34ef56"}])
        )

    def test_an_unknown_top_level_key(self) -> None:
        assert "unknown keys" in refused(spec(sql="SELECT 1"))

    def test_text_operators_on_a_number_column(self) -> None:
        filters = [{"column": "Year", "op": "contains", "value": "20"}]
        assert "op must be one of" in refused(spec(filters=filters))

    def test_a_non_number_for_a_number_column(self) -> None:
        filters = [{"column": "Year", "op": "eq", "value": "twenty"}]
        assert "must be a number" in refused(spec(filters=filters))

    def test_share_of_total_without_group_by(self) -> None:
        assert "needs group_by" in refused(
            spec(measures=[{"fn": "sum", "column": "IMR (%)", "as": "s"}], share_of_total=True)
        )

    def test_too_many_output_columns(self) -> None:
        measures = [{"fn": "avg", "column": "IMR (%)", "as": f"m{i}"} for i in range(5)]
        compare = {"column": "Survey round", "base": "2015-16", "target": "2019-20"}
        assert "at most 20" in refused(
            spec(group_by=["District"], measures=measures, compare=compare)
        )
