"""What a table's stats mean for a reader: descriptions, units, quirks and coverage.

Pure functions, recomputed on every sync pass from the stored stats and the
current metadata; never stored as the source of truth.

- **description**: the publisher's column description, or None when it is an
  upload placeholder ("Description of column <name>", or the older
  "Auto-generated from CSV column <name>"). Publisher text is
  untrusted; views label it so.
- **unit**: a label read from the header or description — %, lakh, crore,
  INR, per 1,000, per lakh, per 100,000. A label only: numbers are never rescaled.
- **quirks**: what an analyst should know before computing — numbers stored as
  text, placeholder values, lakh/crore units, fiscal-year labels, district
  names that don't match our list, wide year columns, total rows, missing
  column descriptions.
- **coverage**: the years and places a table covers, and a one-line text form.

Docs: api/views/query_engine/architecture.md
"""

import re
from typing import Any, Dict, List, Optional, Sequence, Set

from api.services.query_engine.column_roles import KIND_NUMERIC_TEXT, year_sort_key

_PLACEHOLDER_DESCRIPTION = "Description of column "
# What uploads before mid-2025 wrote instead.
_OLD_PLACEHOLDER_DESCRIPTION = "Auto-generated from CSV column "
MAX_COVERAGE_STATES = 40
MAX_YEAR_LABELS = 50

_UNITS = [
    (re.compile(r"\bper\s*1,?00,?000\b|\bper\s*100,?000\b", re.I), "per 100,000"),
    (re.compile(r"\bper\s*lakh\b", re.I), "per lakh"),
    (re.compile(r"\bper\s*1,?000\b", re.I), "per 1,000"),
    (re.compile(r"(\brs\.?|\binr\b|₹|\brupees?\b|रुपये)", re.I), "INR"),
    (re.compile(r"\bcrores?\b|करोड़", re.I), "crore"),
    (re.compile(r"\blakhs?\b|\blacs?\b|लाख", re.I), "lakh"),
    (re.compile(r"%|\bpercent(age)?\b|प्रतिशत", re.I), "%"),
]
_PER_UNITS = {"per 100,000", "per lakh", "per 1,000"}


def clean_description(header: str, description: Optional[str]) -> Optional[str]:
    """The publisher's description, or None when empty or the upload placeholder."""
    text = (description or "").strip()
    fillers = {f"{_PLACEHOLDER_DESCRIPTION}{header}", f"{_OLD_PLACEHOLDER_DESCRIPTION}{header}"}
    if not text or text in fillers:
        return None
    return text


def column_unit(header: str, description: Optional[str]) -> Optional[str]:
    """The unit label read from a column's header (first) or description, or None."""
    for text in (header, description or ""):
        labels = [label for pattern, label in _UNITS if pattern.search(text)]
        if labels:
            return _combine(labels)
    return None


def _combine(labels: List[str]) -> str:
    per = [label for label in labels if label in _PER_UNITS]
    if per:
        return per[0]
    money = "INR" if "INR" in labels else None
    scale = next((label for label in ("crore", "lakh") if label in labels), None)
    if money or scale:
        return " ".join(part for part in (money, scale) if part)
    return labels[0]


def table_quirks(
    stats: Dict[str, Any], descriptions: Dict[str, Optional[str]], units: Dict[str, Optional[str]]
) -> List[Dict[str, Any]]:
    """The table's quirks as ``[{"code", "columns"}]``, in a fixed order (empty when clean)."""
    columns = [c for c in stats.get("columns", []) if c.get("profiled")]
    found: List[Dict[str, Any]] = []

    def add(code: str, names: Sequence[str]) -> None:
        if names:
            found.append({"code": code, "columns": list(names)})

    add("numeric_text", [c["name"] for c in columns if c.get("kind") == KIND_NUMERIC_TEXT])
    add("placeholders", [c["name"] for c in columns if c.get("placeholder_count")])
    add(
        "lakh_crore_units",
        [c["name"] for c in columns if (units.get(c["name"]) or "").endswith(("lakh", "crore"))],
    )
    add(
        "fiscal_year_labels",
        [c["name"] for c in columns if (c.get("time") or {}).get("kind") == "fiscal_year"],
    )
    add(
        "district_name_variants",
        [
            c["name"]
            for c in columns
            if (c.get("geo") or {}).get("level") == "district" and c["geo"].get("unmatched")
        ],
    )
    if stats.get("layout") == "wide_years":
        add("wide_year_columns", stats.get("year_columns", []))
    add("total_rows", [c["name"] for c in columns if c.get("total_markers")])
    add("missing_descriptions", [c["name"] for c in columns if not descriptions.get(c["name"])])
    return found


def district_names(stats: Dict[str, Any]) -> Set[str]:
    """The known district names a table's district columns matched."""
    names: Set[str] = set()
    for column in stats.get("columns", []):
        geo = column.get("geo") or {}
        if column.get("profiled") and geo.get("level") == "district":
            names.update(geo.get("matched", []))
    return names


def coverage(stats: Dict[str, Any]) -> Dict[str, Any]:
    """The years and places a table covers.

    ``year_min`` / ``year_max`` are the true first and last year labels (each
    time column keeps its real range); ``years`` is a sorted sample of at most
    50 labels. ``district_count`` counts distinct matched district names.
    """
    columns = [c for c in stats.get("columns", []) if c.get("profiled")]
    labels: List[Any] = []
    bounds: List[Any] = []
    for column in columns:
        time = column.get("time") or {}
        if time.get("kind") in ("year", "fiscal_year"):
            labels.extend(time.get("values", []))
            bounds.extend([time.get("min"), time.get("max")])
    if stats.get("layout") == "wide_years":
        labels.extend(stats.get("year_columns", []))
        bounds.extend(stats.get("year_columns", []))
    year_labels = sorted({str(label) for label in labels}, key=year_sort_key)[:MAX_YEAR_LABELS]
    ordered_bounds = sorted((str(b) for b in bounds if b is not None), key=year_sort_key)

    states: List[str] = []
    fallback_districts = 0
    geo_level: Optional[str] = None
    for column in columns:
        geo = column.get("geo")
        if not geo:
            continue
        if geo["level"] == "district":
            geo_level = "district"
            fallback_districts = max(fallback_districts, int(geo.get("matched_count", 0)))
            states.extend(geo.get("parent_states", []))
        else:
            geo_level = geo_level or "state"
            states.extend(geo.get("matched", []))
    return {
        "years": year_labels,
        "year_min": ordered_bounds[0] if ordered_bounds else None,
        "year_max": ordered_bounds[-1] if ordered_bounds else None,
        "states": sorted(set(states))[:MAX_COVERAGE_STATES],
        "state_count": len(set(states)),
        "district_count": len(district_names(stats)) or fallback_districts,
        "geo_level": geo_level,
    }


def coverage_text(found: Dict[str, Any]) -> str:
    """One line such as "2015-16 to 2019-20 · 3 districts in Assam" (empty when nothing is known)."""
    parts: List[str] = []
    if found.get("year_min"):
        if found["year_min"] == found["year_max"]:
            parts.append(str(found["year_min"]))
        else:
            parts.append(f"{found['year_min']} to {found['year_max']}")
    states = found.get("states") or []
    where = ", ".join(states[:5]) + (f" and {len(states) - 5} more" if len(states) > 5 else "")
    if found.get("district_count"):
        parts.append(f"{found['district_count']} districts" + (f" in {where}" if where else ""))
    elif states:
        parts.append(f"{found.get('state_count', len(states))} states/UTs: {where}")
    return " · ".join(parts)
