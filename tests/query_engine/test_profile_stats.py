"""Layer 1 (real Postgres data database): profiling tables the real producer built (PS1–PS10).

Every table here comes from ``index_resource_data`` on a fixture CSV, so the
profile describes exactly what uploads produce (pandas types, cleaned
headers, per-upload ``rdt_`` names).
"""

from typing import Any, Callable, Dict

import pytest

from api.models import Resource, ResourceSchema
from api.services.query_engine import column_stats
from api.services.query_engine.errors import QueryTooSlow
from api.services.query_engine.facts import facts_hash, resource_facts
from api.services.query_engine.geography_match import GeographyIndex
from api.services.query_engine.profiles import build_resource_stats
from api.utils.data_indexing import index_resource_data
from tests.data_index.support import replace_file, uses_data_db
from tests.query_engine.conftest import FIXTURES

LONG_ENGLISH = "Percentage of children age 6-59 months who are anaemic (%) in the district"
HINDI = "जिले में एनीमिया से पीड़ित बच्चों का प्रतिशत लाख में"


def by_name(stats: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {column["name"]: column for column in stats["columns"]}


def reload(resource: Resource) -> Resource:
    return Resource.objects.select_related("dataset", "resourcedatatable").get(pk=resource.pk)


@uses_data_db
def test_counts_and_numbers_match_the_file(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    stats = build_resource_stats(make_table_resource("district_health.csv"), geography)
    columns = by_name(stats)

    assert stats["row_count"] == 8
    assert stats["stats_complete"] is True
    imr = columns["IMR (%)"]
    assert imr["storage_type"] == "double precision"
    assert (imr["kind"], imr["role"]) == ("numeric", "measure")
    assert (imr["non_null"], imr["distinct"], imr["null_pct"]) == (8, 8, 0.0)
    # (32.5 + 30.5 + 25 + 22 + 40 + 38 + 33 + 30) / 8
    assert (imr["min"], imr["max"], imr["mean"]) == (22.0, 40.0, 31.375)
    assert columns["Remarks"]["null_pct"] == 25.0


@uses_data_db
def test_numbers_stored_as_text_are_flagged_with_their_odd_tokens(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    columns = by_name(build_resource_stats(make_table_resource("district_health.csv"), geography))

    population = columns["Population"]
    assert population["storage_type"] == "text"
    assert population["kind"] == "numeric_text"
    assert population["role"] == "measure"
    assert population["placeholder_count"] == 2
    assert (population["min"], population["max"]) == (123456.0, 540500.0)
    assert population["non_numeric_tokens"] == ["-", "n.a."]
    # Mostly words with one number: stays text.
    assert columns["Remarks"]["kind"] == "text"
    assert columns["Remarks"]["non_numeric_tokens"] == []


@uses_data_db
def test_integer_years_and_fiscal_year_labels_are_detected(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    columns = by_name(build_resource_stats(make_table_resource("district_health.csv"), geography))

    assert columns["Year"]["role"] == "time_year"
    assert columns["Year"]["time"] == {
        "kind": "year",
        "values": [2015, 2019],
        "min": 2015,
        "max": 2019,
    }
    assert columns["Survey round"]["role"] == "time_fiscal_year"
    assert columns["Survey round"]["time"]["values"] == ["2015-16", "2019-20"]


@uses_data_db
def test_place_columns_are_matched_against_known_geographies(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    columns = by_name(build_resource_stats(make_table_resource("district_health.csv"), geography))

    district = columns["District"]
    assert district["role"] == "geography_district"
    assert district["geo"]["level"] == "district"
    assert district["geo"]["match_pct"] == 66.7
    assert district["geo"]["unmatched"] == [
        {"value": "Kamrup Metro", "closest": "Kamrup Metropolitan"}
    ]
    assert district["geo"]["parent_states"] == ["Assam"]
    assert district["total_markers"] == ["Total"]
    assert columns["State"]["role"] == "geography_state"
    assert columns["State"]["geo"]["matched"] == ["Assam"]


@uses_data_db
def test_identical_data_gives_the_same_facts_hash_even_after_a_re_upload(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    resource = make_table_resource("district_health.csv")
    first = facts_hash(resource_facts(resource, build_resource_stats(resource, geography)))
    again = facts_hash(resource_facts(resource, build_resource_stats(resource, geography)))
    old_table = resource.resourcedatatable.id

    replace_file(resource, (FIXTURES / "district_health.csv").read_bytes())
    assert index_resource_data(reload(resource)) is not None
    resource = reload(resource)
    after_upload = facts_hash(resource_facts(resource, build_resource_stats(resource, geography)))

    assert resource.resourcedatatable.id != old_table
    assert first == again == after_upload


@uses_data_db
def test_a_column_batch_that_times_out_leaves_the_profile_incomplete_not_failed(
    make_table_resource: Callable, geography: GeographyIndex, monkeypatch: Any
) -> None:
    resource = make_table_resource("district_health.csv")
    real_read = column_stats._read_aggregates
    monkeypatch.setattr(column_stats, "STATS_BATCH_COLUMNS", 4)

    def slow_second_batch(table: str, batch: list) -> Dict:
        if any(column.header == "IMR (%)" for column in batch):
            raise QueryTooSlow()
        return real_read(table, batch)

    monkeypatch.setattr(column_stats, "_read_aggregates", slow_second_batch)
    stats = build_resource_stats(resource, geography)
    columns = by_name(stats)

    assert stats["stats_complete"] is False
    assert columns["IMR (%)"]["stats_unavailable"] is True
    assert columns["IMR (%)"]["role"] == "measure"
    # The batch is retried in smaller pieces: only the slow column loses its stats.
    assert "distinct" in columns["District"]
    assert columns["Stunting (%)"]["distinct"] == 7
    assert sum(1 for c in stats["columns"] if c.get("stats_unavailable")) == 1
    assert any("took too long" in note for note in stats["notes"])


@uses_data_db
def test_infinite_values_become_null_with_a_note_and_an_empty_column_is_handled(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    stats = build_resource_stats(make_table_resource("odd_values.csv"), geography)
    columns = by_name(stats)

    ratio = columns["Ratio"]
    assert ratio["min"] == 1.5
    assert ratio["max"] is None and ratio["mean"] is None
    assert ratio["non_finite"] is True
    assert any("infinite" in note for note in stats["notes"])
    empty = columns["Empty"]
    assert (empty["non_null"], empty["distinct"], empty["min"], empty["null_pct"]) == (
        0,
        0,
        None,
        100.0,
    )


@uses_data_db
def test_reads_a_per_upload_table(make_table_resource: Callable, geography: GeographyIndex) -> None:
    resource = make_table_resource("wide_years.csv")
    assert resource.resourcedatatable.table_name.startswith("rdt_")

    stats = build_resource_stats(resource, geography)

    assert stats["row_count"] == 2
    assert stats["layout"] == "wide_years"
    assert stats["year_columns"] == ["2015-16", "2016-17", "2019-20"]


@uses_data_db
def test_long_english_and_hindi_headers_keep_their_type_description_and_unit(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    resource = make_table_resource("long_headers.csv")
    ResourceSchema.objects.filter(resource=resource, field_name=LONG_ENGLISH).update(
        description="Share of children with anaemia"
    )
    ResourceSchema.objects.filter(resource=resource, field_name=HINDI).update(
        description="लाख में संख्या"
    )

    stats = build_resource_stats(resource, geography)
    facts = {c["name"]: c for c in resource_facts(resource, stats)["columns"]}

    for header in (LONG_ENGLISH, HINDI):
        column = by_name(stats)[header]
        assert column["available"] is True
        assert column["storage_type"] == "double precision"
        assert column["role"] == "measure"
    assert facts[LONG_ENGLISH]["description"] == "Share of children with anaemia"
    assert facts[LONG_ENGLISH]["unit"] == "%"
    assert facts[HINDI]["description"] == "लाख में संख्या"
    assert facts[HINDI]["unit"] == "lakh"


@uses_data_db
def test_a_very_wide_table_profiles_the_first_300_columns(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    header = ",".join(f"c{index:03d}" for index in range(320))
    rows = "\n".join(",".join(str(row + index) for index in range(320)) for row in range(2))
    resource = make_table_resource(f"{header}\n{rows}\n".encode())

    stats = build_resource_stats(resource, geography)

    profiled = [c for c in stats["columns"] if c.get("profiled")]
    not_profiled = [c for c in stats["columns"] if not c.get("profiled")]
    assert len(profiled) == 300
    assert [c["name"] for c in not_profiled] == [f"c{index:03d}" for index in range(300, 320)]
    assert all(c["available"] for c in not_profiled)
    assert any("not profiled" in note for note in stats["notes"])


@uses_data_db
def test_a_text_year_column_with_a_dash_is_still_time(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    stats = build_resource_stats(
        make_table_resource(b"District,Year,Cases\nKamrup,2015,1\nNagaon,2016,2\nDibrugarh,-,3\n"),
        geography,
    )
    year = by_name(stats)["Year"]
    assert year["storage_type"] == "text"
    assert year["role"] == "time_year"
    assert year["time"]["values"] == [2015, 2016]


@uses_data_db
def test_columns_with_over_1000_values_get_samples_and_odd_tokens(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    lines = ["Village,Households"]
    for index in range(1500):
        households = "n.a." if index % 500 == 0 else f"{index + 1:,}"
        lines.append(f'Village {index:04d},"{households}"')
    stats = build_resource_stats(make_table_resource(("\n".join(lines) + "\n").encode()), geography)
    columns = by_name(stats)

    village = columns["Village"]
    assert village["distinct"] == 1500 and village["top_values"] is None
    assert len(village["examples"]) == 3
    households = columns["Households"]
    assert households["kind"] == "numeric_text"
    assert households["non_numeric_tokens"] == ["n.a."]
    assert households["max"] == 1500.0


@uses_data_db
def test_past_the_tables_time_budget_columns_are_left_without_stats(
    make_table_resource: Callable, geography: GeographyIndex, monkeypatch: Any
) -> None:
    resource = make_table_resource("district_health.csv")
    monkeypatch.setattr(column_stats, "STATS_BATCH_COLUMNS", 2)

    stats = build_resource_stats(resource, geography, time_budget_seconds=0)

    assert stats["stats_complete"] is False
    assert all(c.get("stats_unavailable") for c in stats["columns"])
