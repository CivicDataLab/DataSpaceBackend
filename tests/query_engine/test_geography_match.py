"""Layer 2: recognising place columns from their header and values (O2)."""

from api.services.query_engine.geography_match import GeographyIndex, match_places

INDEX = GeographyIndex(
    states={"assam": "Assam", "bihar": "Bihar"},
    districts={"kamrup": "Kamrup", "nagaon": "Nagaon", "patna": "Patna"},
    state_of_district={"Kamrup": "Assam", "Nagaon": "Assam", "Patna": "Bihar"},
)


def test_values_alone_can_make_a_district_column() -> None:
    found = match_places("Name", ["Kamrup", "Nagaon district", "Patna", "Elsewhere"], INDEX)
    assert found["level"] == "district" and found["match_pct"] == 75.0
    assert found["parent_states"] == ["Assam", "Bihar"]


def test_a_place_header_with_codes_is_not_a_place_column() -> None:
    assert match_places("District code", ["AS01", "AS02", "BR01"], INDEX) is None


def test_an_underscored_header_counts_as_a_place_header() -> None:
    found = match_places("district_name", ["Kamrup", "Unknown one", "Unknown two"], INDEX)
    assert found["level"] == "district"


def test_placeholders_and_total_rows_are_left_out_of_the_share() -> None:
    found = match_places("Area", ["Kamrup", "Nagaon", "Total", "-", "NA"], INDEX)
    assert found["match_pct"] == 100.0


def test_an_ordinary_text_column_is_not_a_place() -> None:
    assert match_places("Remarks", ["good", "fair"], INDEX) is None
