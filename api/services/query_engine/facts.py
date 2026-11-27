"""The facts bundle for a table or a dataset, and its hash.

Facts are what a summary may say and what a search card is built from: the
dataset's title, organisation, sectors, tags and places; the table's name and
description; row and column counts; per column its name, description, kind,
role, unit, min / max, and distinct count for place, time and category
columns (so "covers 36 states" can be checked); coverage; quirks. A dataset's
facts add its tables and its non-tabular resources (name and format) and the
union of the tables' coverage.

Pure: everything comes from objects the caller already loaded (the sync pass
prefetches them). Facts carry no ids or timestamps, so ``facts_hash`` (SHA-256
of canonical JSON) stays the same when identical data is uploaded again, and
changes when any description, name, tag or stat changes.

Docs: api/views/query_engine/architecture.md
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from api.models import Dataset, Resource
from api.services.query_engine.column_roles import year_sort_key
from api.services.query_engine.profile_overlay import (
    MAX_YEAR_LABELS,
    clean_description,
    column_unit,
    coverage,
    coverage_text,
    district_names,
    table_quirks,
)

_DISTINCT_ROLES = ("geography_state", "geography_district", "time_year", "time_fiscal_year")
_DISTINCT_FOR = _DISTINCT_ROLES + ("dimension",)


def facts_hash(facts: Dict[str, Any]) -> str:
    """SHA-256 of the facts as canonical JSON (sorted keys, no spaces)."""
    canonical = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dataset_metadata(dataset: Dataset) -> Dict[str, Any]:
    """The dataset's title, description, organisation, sectors, tags and places (sorted)."""
    return {
        "title": dataset.title or "",
        "description": dataset.description or "",
        "organization": dataset.organization.name if dataset.organization else "",
        "sectors": sorted(sector.name for sector in dataset.sectors.all()),
        "tags": sorted(tag.value for tag in dataset.tags.all()),
        "places": sorted(place.name for place in dataset.geographies.all()),
    }


def column_descriptions(resource: Resource) -> Dict[str, Optional[str]]:
    """Each column's publisher description (None for empty or the upload placeholder)."""
    return {
        row.field_name: clean_description(row.field_name, row.description)
        for row in resource.resourceschema_set.all()
    }


def resource_facts(resource: Resource, stats: Dict[str, Any]) -> Dict[str, Any]:
    """The facts for one profiled table (its dataset's metadata included)."""
    descriptions = column_descriptions(resource)
    units = {
        c["name"]: column_unit(c["name"], descriptions.get(c["name"])) for c in stats["columns"]
    }
    found_coverage = coverage(stats)
    return {
        "level": "resource",
        "dataset": dataset_metadata(resource.dataset),
        "table": {"name": resource.name, "description": resource.description or ""},
        "row_count": stats.get("row_count", 0),
        "column_count": len(stats["columns"]),
        "columns": [_column_facts(c, descriptions, units) for c in stats["columns"]],
        "coverage": found_coverage,
        "coverage_text": coverage_text(found_coverage),
        "quirks": table_quirks(stats, descriptions, units),
        "layout": stats.get("layout"),
        "analysable": bool(stats.get("analysable")),
    }


def _column_facts(
    column: Dict[str, Any], descriptions: Dict[str, Optional[str]], units: Dict[str, Optional[str]]
) -> Dict[str, Any]:
    name = column["name"]
    if not column.get("profiled"):
        return {"name": name, "profiled": False}
    facts: Dict[str, Any] = {
        "name": name,
        "description": descriptions.get(name),
        "kind": column.get("kind"),
        "role": column.get("role"),
        "unit": units.get(name),
    }
    if column.get("min") is not None or column.get("max") is not None:
        facts["min"] = column.get("min")
        facts["max"] = column.get("max")
    if column.get("role") in _DISTINCT_FOR:
        facts["distinct"] = column.get("distinct")
    return facts


def table_order(pair: Tuple[Resource, Any]) -> Tuple[str, str]:
    """How a dataset's tables are listed: by name, then id (stable when names repeat)."""
    return (pair[0].name, str(pair[0].id))


def dataset_facts(
    dataset: Dataset, tables: Sequence[Tuple[Resource, Optional[Dict[str, Any]]]]
) -> Dict[str, Any]:
    """The facts for a dataset: its metadata, its tables, its other resources and their coverage.

    ``tables`` pairs each analysable table with its stats (None while not yet
    profiled). Every other resource is listed by name and format.
    """
    table_ids = {resource.id for resource, _ in tables}
    table_facts: List[Dict[str, Any]] = []
    years: List[str] = []
    bounds: List[str] = []
    states: List[str] = []
    districts: Set[str] = set()
    fallback_districts = 0
    for resource, stats in sorted(tables, key=table_order):
        found = coverage(stats) if stats else coverage({})
        years.extend(found["years"])
        bounds.extend(b for b in (found["year_min"], found["year_max"]) if b)
        states.extend(found["states"])
        districts |= district_names(stats or {})
        fallback_districts = max(fallback_districts, found["district_count"])
        table_facts.append(
            {
                "name": resource.name,
                "description": resource.description or "",
                "row_count": (stats or {}).get("row_count"),
                "column_count": len((stats or {}).get("columns", [])),
                "coverage_text": coverage_text(found),
                "analysable": bool((stats or {}).get("analysable")),
            }
        )
    others = sorted(
        (
            {"name": resource.name, "format": _format_of(resource)}
            for resource in dataset.resources.all()
            if resource.id not in table_ids
        ),
        key=lambda item: (item["name"], item["format"]),
    )
    union = _union_coverage(years, bounds, states, len(districts) or fallback_districts)
    return {
        "level": "dataset",
        "dataset": dataset_metadata(dataset),
        "tables": table_facts,
        "other_resources": others,
        "coverage": union,
        "coverage_text": coverage_text(union),
    }


def _format_of(resource: Resource) -> str:
    details = getattr(resource, "resourcefiledetails", None)
    if details is not None and details.format:
        return str(details.format).lower()
    return str(resource.type).lower()


def _union_coverage(
    years: List[str], bounds: List[str], states: List[str], district_count: int
) -> Dict[str, Any]:
    year_labels = sorted(set(years), key=year_sort_key)[:MAX_YEAR_LABELS]
    ordered_bounds = sorted(set(bounds), key=year_sort_key)
    state_names = sorted(set(states))
    return {
        "years": year_labels,
        "year_min": ordered_bounds[0] if ordered_bounds else None,
        "year_max": ordered_bounds[-1] if ordered_bounds else None,
        "states": state_names,
        "state_count": len(state_names),
        "district_count": district_count,
        "geo_level": "district" if district_count else ("state" if state_names else None),
    }
