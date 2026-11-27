"""A profile's stats shaped like district_health.csv's, for spec and compiler tests."""

from typing import Any, Dict


def col(name: str, kind: str, role: str, storage: str = "text", **extra: Any) -> Dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "role": role,
        "storage_type": storage,
        "available": True,
        "profiled": True,
        **extra,
    }


def health_stats(**changes: Any) -> Dict[str, Any]:
    stats = {
        "row_count": 8,
        "layout": "long",
        "year_columns": [],
        "analysable": True,
        "not_analysable_reasons": [],
        "columns": [
            col("State", "text", "geography_state"),
            col("District", "text", "geography_district", total_markers=["Total"], distinct=4),
            col("Year", "numeric", "time_year", "bigint"),
            col("Survey round", "text", "time_fiscal_year"),
            col("IMR (%)", "numeric", "measure", "double precision"),
            col("Stunting (%)", "numeric", "measure", "double precision"),
            col("Population", "numeric_text", "measure"),
            col("Remarks", "text", "dimension"),
            {"name": "Gone", "available": False, "profiled": False},
            {"name": "c999", "available": True, "profiled": False, "storage_type": "bigint"},
        ],
    }
    stats.update(changes)
    return stats


def wide_stats() -> Dict[str, Any]:
    return {
        "row_count": 2,
        "layout": "wide_years",
        "year_columns": ["2015-16", "2016-17", "2019-20"],
        "analysable": True,
        "columns": [
            col("District", "text", "geography_district"),
            col("2015-16", "numeric", "measure", "bigint"),
            col("2016-17", "numeric", "measure", "bigint"),
            col("2019-20", "numeric", "measure", "bigint"),
        ],
    }
