"""Turning an analysis query's raw rows into the response the query engine cites.

Renames the statement's short aliases back to full headers, turns numbers
into JSON (rounded to 6 decimals; infinite or NaN → null with a note), moves
the hidden "rows ignored" counts of numeric-text measures into
``non_numeric_rows_ignored`` and a note, attaches units (a number keeps its
column's unit; the change in a percentage is in "percentage points";
percentage changes and shares are "%"), and adds the exact SQL
that ran, the normalised spec and the provenance (dataset, resource, data
table, facts hash). No arithmetic on result values happens here.

Docs: api/views/query_engine/architecture.md
"""

from typing import Any, Dict, List, Optional

from api.models import Resource, ResourceProfile
from api.services.query_engine.column_stats import to_json_number
from api.services.query_engine.data_reader import ReadResult
from api.services.query_engine.facts import column_descriptions
from api.services.query_engine.profile_overlay import column_unit
from api.services.query_engine.query_compiler import CompiledQuery
from api.services.query_engine.query_spec import QuerySpec


def output_units(spec: QuerySpec, resource: Resource) -> Dict[str, Optional[str]]:
    """The unit of each output column that has one."""
    descriptions = column_descriptions(resource)

    def unit_of(column: Optional[str]) -> Optional[str]:
        return column_unit(column, descriptions.get(column)) if column else None

    units: Dict[str, Optional[str]] = {}
    for column in list(spec.group_by) + list(spec.columns):
        units[column] = unit_of(column)
    for measure in spec.measures:
        if measure.fn in ("count", "count_distinct"):
            unit = None
        elif spec.compare is not None and spec.compare.wide:
            unit = unit_of(spec.compare.base_column)
        else:
            unit = unit_of(measure.column)
        a = measure.alias
        for name in (a, f"{a}__base", f"{a}__target"):
            units[name] = unit
        # The difference between two percentages is in points, not a percentage of anything.
        units[f"{a}__change"] = "percentage points" if unit == "%" else unit
        units[f"{a}__pct_change"] = "%"
        units[f"{a}__share_pct"] = "%"
    return {name: unit for name, unit in units.items() if unit}


def query_response(
    spec: QuerySpec,
    compiled: CompiledQuery,
    result: ReadResult,
    resource: Resource,
    profile: ResourceProfile,
) -> Dict[str, Any]:
    """The response body: columns, rows, notes, units, SQL, normalised spec, provenance."""
    visible = [
        i for i, alias in enumerate(compiled.aliases) if alias not in compiled.ignored_aliases
    ]
    hidden = {
        i: compiled.ignored_aliases[alias]
        for i, alias in enumerate(compiled.aliases)
        if alias in compiled.ignored_aliases
    }
    notes: List[str] = list(compiled.notes)
    non_finite = False
    rows: List[List[Any]] = []
    ignored: Dict[str, int] = {}
    for raw in result.rows:
        row = []
        for index in visible:
            value, was_non_finite = to_json_number(raw[index])
            non_finite |= was_non_finite
            row.append(value)
        rows.append(row)
        for index, alias in hidden.items():
            ignored[alias] = int(raw[index] or 0)
    for alias, count in ignored.items():
        if count:
            notes.append(f"{alias}: {count} rows with values that aren't numbers were ignored")
    if non_finite:
        notes.append("infinite or undefined results are shown as null")
    # Output names follow the visible columns in order (hidden counts carry no name).
    names = list(compiled.output_columns)
    units = output_units(spec, resource)
    return {
        "columns": names,
        "rows": rows,
        "row_count": len(rows),
        "truncated": result.truncated,
        "notes": notes,
        "units": {name: units[name] for name in names if name in units},
        "non_numeric_rows_ignored": ignored,
        "sql": result.sql,
        "query_spec": spec.normalised(),
        "provenance": {
            "dataset_id": str(resource.dataset_id),
            "resource_id": str(resource.id),
            "data_table_id": str(profile.data_table_id),
            "facts_hash": profile.facts_hash,
        },
    }
