"""Layer 2: column kinds, roles, time, layout, units, quirks and analysability (RO1).

Each detector gets a fixture that should make it fire, and a clean one that shouldn't.
"""

from typing import Any, Dict, List

import pytest

from api.services.query_engine.column_roles import (
    detect_kind,
    detect_layout,
    detect_role,
    detect_time,
    is_total_marker,
    not_analysable_reasons,
)
from api.services.query_engine.profile_overlay import (
    clean_description,
    column_unit,
    coverage,
    coverage_text,
    table_quirks,
)


class TestKind:
    @pytest.mark.parametrize(
        "storage,counts,kind",
        [
            ("bigint", (5, 0, 0), "numeric"),
            ("double precision", (5, 0, 0), "numeric"),
            ("timestamp without time zone", (5, 0, 0), "date"),
            ("boolean", (5, 0, 0), "boolean"),
            ("text", (10, 1, 9), "numeric_text"),
            ("text", (10, 0, 8), "text"),
            ("text", (2, 2, 0), "text"),
            ("text", (0, 0, 0), "text"),
        ],
    )
    def test_kind(self, storage: str, counts: tuple, kind: str) -> None:
        assert detect_kind(storage, *counts) == kind


class TestTime:
    def test_integer_years_under_a_year_header(self) -> None:
        assert detect_time("Year", "numeric", ["2019", "2015"])["values"] == [2015, 2019]

    def test_integers_without_a_year_header_are_not_time(self) -> None:
        assert detect_time("Count", "numeric", ["2019", "2015"]) is None

    def test_numbers_outside_the_year_range_are_not_years(self) -> None:
        assert detect_time("Year", "numeric", ["12", "15"]) is None

    def test_text_years(self) -> None:
        assert detect_time("Period", "text", ["2019", "2021"])["kind"] == "year"

    def test_fiscal_years(self) -> None:
        found = detect_time("Round", "text", ["FY 2019-20", "2015-16"])
        assert found["kind"] == "fiscal_year"
        assert found["values"] == ["2015-16", "FY 2019-20"]

    def test_ordinary_text_is_not_time(self) -> None:
        assert detect_time("Remarks", "text", ["good", "fair"]) is None


class TestRole:
    def test_place_wins(self) -> None:
        assert detect_role("District", "text", {"level": "district"}, None) == "geography_district"

    def test_time_comes_next(self) -> None:
        assert detect_role("Year", "numeric", None, {"kind": "year"}) == "time_year"

    @pytest.mark.parametrize("header", ["State code", "S.No", "Sl. No.", "district_id", "LGD code"])
    def test_codes_and_serial_numbers_are_identifiers(self, header: str) -> None:
        assert detect_role(header, "numeric", None, None) == "identifier"

    def test_numbers_are_measures_and_text_is_a_dimension(self) -> None:
        assert detect_role("IMR (%)", "numeric", None, None) == "measure"
        assert detect_role("Population", "numeric_text", None, None) == "measure"
        assert detect_role("Remarks", "text", None, None) == "dimension"


def test_wide_layout_needs_three_year_headed_number_columns() -> None:
    wide = [{"name": n, "kind": "numeric"} for n in ("2015-16", "2016-17", "FY 2019-20")]
    assert detect_layout(wide) == ("wide_years", ["2015-16", "2016-17", "FY 2019-20"])
    assert detect_layout(wide[:2] + [{"name": "Total", "kind": "numeric"}]) == ("long", [])
    assert detect_layout([{"name": n, "kind": "text"} for n in ("2015", "2016", "2017")]) == (
        "long",
        [],
    )


def test_total_markers() -> None:
    assert is_total_marker("Grand  Total")
    assert is_total_marker("All India")
    assert not is_total_marker("Kamrup")


def test_analysable_needs_rows_and_a_measure() -> None:
    measure = [{"role": "measure"}]
    assert not_analysable_reasons(10, measure) == []
    assert not_analysable_reasons(0, measure) == ["empty"]
    assert not_analysable_reasons(10, [{"role": "dimension"}]) == ["no_numeric_measure"]


class TestUnitsAndDescriptions:
    @pytest.mark.parametrize(
        "header,description,unit",
        [
            ("IMR (%)", None, "%"),
            ("Expenditure (Rs. lakh)", None, "INR lakh"),
            ("Budget", "Amount in crore", "crore"),
            ("Deaths per 1,000 live births", None, "per 1,000"),
            ("Cases per lakh population", None, "per lakh"),
            ("कुल राशि करोड़ में", None, "crore"),
            ("District", "Name of the district", None),
        ],
    )
    def test_unit_labels(self, header: str, description: Any, unit: Any) -> None:
        assert column_unit(header, description) == unit

    def test_the_upload_placeholder_is_no_description(self) -> None:
        assert clean_description("IMR", "Description of column IMR") is None
        assert clean_description("IMR", "  ") is None
        assert clean_description("IMR", "Infant deaths per 1,000") == "Infant deaths per 1,000"


def column(**fields: Any) -> Dict[str, Any]:
    return {"profiled": True, "kind": "numeric", "placeholder_count": 0, **fields}


class TestQuirks:
    def codes(self, stats: Dict[str, Any], units: Dict[str, Any] = {}) -> List[str]:
        descriptions = {c["name"]: "described" for c in stats["columns"]}
        return [q["code"] for q in table_quirks(stats, descriptions, units)]

    def test_a_clean_table_has_no_quirks(self) -> None:
        assert self.codes({"columns": [column(name="IMR")]}) == []

    @pytest.mark.parametrize(
        "stats,units,code",
        [
            ({"columns": [column(name="P", kind="numeric_text")]}, {}, "numeric_text"),
            ({"columns": [column(name="P", placeholder_count=2)]}, {}, "placeholders"),
            ({"columns": [column(name="Spend")]}, {"Spend": "INR lakh"}, "lakh_crore_units"),
            (
                {"columns": [column(name="R", kind="text", time={"kind": "fiscal_year"})]},
                {},
                "fiscal_year_labels",
            ),
            (
                {
                    "columns": [
                        column(
                            name="D",
                            kind="text",
                            geo={"level": "district", "unmatched": [{"value": "x"}]},
                        )
                    ]
                },
                {},
                "district_name_variants",
            ),
            (
                {
                    "columns": [column(name="2015")],
                    "layout": "wide_years",
                    "year_columns": ["2015"],
                },
                {},
                "wide_year_columns",
            ),
            ({"columns": [column(name="D", total_markers=["Total"])]}, {}, "total_rows"),
        ],
    )
    def test_each_quirk_fires_on_its_own_fixture(
        self, stats: Dict[str, Any], units: Dict[str, Any], code: str
    ) -> None:
        assert self.codes(stats, units) == [code]

    def test_missing_descriptions(self) -> None:
        stats = {"columns": [column(name="IMR")]}
        found = table_quirks(stats, {"IMR": None}, {})
        assert found == [{"code": "missing_descriptions", "columns": ["IMR"]}]


def test_coverage_and_its_text() -> None:
    stats = {
        "columns": [
            column(
                name="Round",
                kind="text",
                time={
                    "kind": "fiscal_year",
                    "values": ["2015-16", "2019-20"],
                    "min": "2015-16",
                    "max": "2019-20",
                },
            ),
            column(
                name="District",
                kind="text",
                geo={
                    "level": "district",
                    "matched": ["Kamrup", "Nagaon", "Dibrugarh"],
                    "matched_count": 3,
                    "parent_states": ["Assam"],
                },
            ),
        ]
    }
    found = coverage(stats)
    assert (found["year_min"], found["year_max"], found["district_count"]) == (
        "2015-16",
        "2019-20",
        3,
    )
    assert coverage_text(found) == "2015-16 to 2019-20 · 3 districts in Assam"
    assert coverage_text(coverage({"columns": []})) == ""


class TestYearFixes:
    def test_a_long_series_keeps_its_true_range_beyond_the_50_value_sample(self) -> None:
        found = detect_time("Year", "numeric", [str(y) for y in range(1901, 2021)])
        assert (found["min"], found["max"], len(found["values"])) == (1901, 2020, 50)
        stats = {"columns": [column(name="Year", time=found)]}
        assert (coverage(stats)["year_min"], coverage(stats)["year_max"]) == ("1901", "2020")
        assert coverage_text(coverage(stats)) == "1901 to 2020"

    def test_years_written_as_text_with_a_placeholder_are_a_time_column(self) -> None:
        # The pipeline calls such a column numbers-as-text; it is still the year.
        found = detect_time("Year", "numeric_text", ["2015", "2016", "2017", "-"])
        assert found["kind"] == "year" and found["values"] == [2015, 2016, 2017]
        assert detect_role("Year", "numeric_text", None, found) == "time_year"

    def test_an_underscored_year_header_counts(self) -> None:
        assert detect_time("survey_year", "numeric", ["2015", "2019"])["kind"] == "year"
        assert detect_time("academic_year", "numeric", ["2015"])["kind"] == "year"

    def test_monthly_labels_are_not_fiscal_years(self) -> None:
        assert detect_time("Month", "text", ["2019-01", "2019-02", "2019-12"]) is None
        assert detect_time("Round", "text", ["1999-2000", "2019-20"])["kind"] == "fiscal_year"

    def test_monthly_headers_do_not_make_a_wide_table(self) -> None:
        monthly = [{"name": n, "kind": "numeric"} for n in ("2019-01", "2019-02", "2019-03")]
        assert detect_layout(monthly) == ("long", [])


def test_the_older_upload_filler_is_no_description() -> None:
    assert clean_description("IMR", "Auto-generated from CSV column IMR") is None


def test_districts_are_counted_once_across_a_datasets_tables() -> None:
    from api.services.query_engine.facts import _union_coverage
    from api.services.query_engine.profile_overlay import district_names

    assam = {
        "columns": [
            column(
                name="D",
                kind="text",
                geo={
                    "level": "district",
                    "matched": ["Kamrup", "Nagaon"],
                    "matched_count": 2,
                    "parent_states": ["Assam"],
                },
            )
        ]
    }
    bihar = {
        "columns": [
            column(
                name="D",
                kind="text",
                geo={
                    "level": "district",
                    "matched": ["Patna", "Gaya", "Nagaon"],
                    "matched_count": 3,
                    "parent_states": ["Bihar"],
                },
            )
        ]
    }
    union = district_names(assam) | district_names(bihar)
    assert len(union) == 4
    assert coverage(bihar)["district_count"] == 3
    assert (
        _union_coverage(["2015"], ["2015", "2019"], ["Assam", "Bihar"], len(union))[
            "district_count"
        ]
        == 4
    )
