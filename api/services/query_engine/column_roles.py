"""What each column of a table is: its kind, its role, its time values, and the table's layout.

Pure functions over counts and values the stats statements already read:

- **kind**: numeric (number storage) | date | boolean | numeric_text (text where
  at least 90 % of the non-placeholder values look like numbers — "1,23,456",
  "12.5 %") | text.
- **time**: a year column (integer years 1900–2100 under a year-like header, or
  text that is all 4-digit years), a fiscal-year column ("2019-20", "FY 2019-20"),
  or a date column; with its sorted values (≤ 50), min and max.
- **role**: geography_state | geography_district (from the place match) |
  time_year | time_fiscal_year | time_date | identifier (codes, serial numbers)
  | measure (numbers) | dimension (other text).
- **layout**: wide_years when at least 3 number columns are headed by years or
  fiscal years ("2015-16", "2019"); otherwise long.
- **total markers**: values such as "Total", "Grand Total", "All India".
- **analysable**: needs rows and at least one measure.

Docs: api/views/query_engine/architecture.md
"""

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

NUMERIC_TYPES = ("bigint", "integer", "smallint", "double precision", "real", "numeric")
NUMERIC_TEXT_SHARE = 0.9
FISCAL_YEAR_SHARE = 0.9
WIDE_YEAR_COLUMNS = 3
MAX_TIME_VALUES = 50
YEAR_RANGE = (1900, 2100)

KIND_NUMERIC = "numeric"
KIND_NUMERIC_TEXT = "numeric_text"
KIND_TEXT = "text"
KIND_DATE = "date"
KIND_BOOLEAN = "boolean"
NUMBER_KINDS = (KIND_NUMERIC, KIND_NUMERIC_TEXT)

ROLE_MEASURE = "measure"
ROLE_DIMENSION = "dimension"
ROLE_IDENTIFIER = "identifier"

# Underscores count as word breaks ("survey_year"), so these use [^a-z], not word boundaries.
_YEAR_HEADER = re.compile(r"(^|[^a-z])(year|years|yr|fy)([^a-z]|$)|वर्ष|साल", re.IGNORECASE)
_FISCAL_YEAR = re.compile(r"^\s*(fy\s*)?((19|20)\d{2})\s*[-–/]\s*(\d{2}|\d{4})\s*$", re.I)
_YEAR = re.compile(r"^\s*(19|20)\d{2}\s*$")
YEAR_SHARE = 0.9
# Cell values that stand for "no value"; compared lower-cased and trimmed.
PLACEHOLDERS = ["na", "n/a", "n.a.", "n.a", "-", "--", "---", "nil", "..", "...", "null", "none"]
_IDENTIFIER_HEADER = re.compile(
    r"(^|[\s_(])(id|code|lgd|s\.?\s?no\.?|sl\.?\s?no\.?|sr\.?\s?no\.?|serial(\s?no\.?)?)"
    r"($|[\s_).])",
    re.IGNORECASE,
)

TOTAL_MARKERS = (
    "total",
    "grand total",
    "all india",
    "india",
    "india total",
    "state total",
    "district total",
    "overall",
)


def detect_kind(storage_type: str, non_null: int, placeholders: int, numeric_like: int) -> str:
    """The column's kind from its storage type and, for text, how many values look numeric."""
    if storage_type.startswith(NUMERIC_TYPES):
        return KIND_NUMERIC
    if storage_type.startswith("timestamp") or storage_type == "date":
        return KIND_DATE
    if storage_type == "boolean":
        return KIND_BOOLEAN
    candidates = non_null - placeholders
    if candidates > 0 and numeric_like >= NUMERIC_TEXT_SHARE * candidates:
        return KIND_NUMERIC_TEXT
    return KIND_TEXT


def is_total_marker(value: Any) -> bool:
    """Whether a cell value is a total row's label ("Total", "All India", …)."""
    return isinstance(value, str) and " ".join(value.lower().split()) in TOTAL_MARKERS


def total_markers_in(values: Sequence[str]) -> List[str]:
    """The total-row labels among a column's distinct values, as written."""
    return sorted({value for value in values if is_total_marker(value)})


def is_placeholder(value: Any) -> bool:
    """Whether a cell value is one of the "no value" placeholders (NA, -, nil, …)."""
    return str(value).strip().lower() in PLACEHOLDERS


def is_fiscal_year(label: str) -> bool:
    """A fiscal-year label whose second part is the next year: "2019-20", "FY 1999-2000"."""
    found = _FISCAL_YEAR.match(label)
    if not found:
        return False
    start, end = int(found.group(2)), found.group(4)
    return int(end) == start + 1 if len(end) == 4 else int(end) == (start + 1) % 100


def _year_of(value: str, kind: str) -> Optional[int]:
    if kind == KIND_NUMERIC:
        try:
            number = float(value)
        except ValueError:
            return None
        year = int(number)
        ok = number == year and YEAR_RANGE[0] <= year <= YEAR_RANGE[1]
        return year if ok else None
    return int(value) if _YEAR.match(value) else None


def detect_time(header: str, kind: str, values: Optional[Sequence[str]]) -> Optional[Dict]:
    """The column's time kind and values, or None when it isn't a time column.

    ``values`` are the column's distinct non-null values as text (None when
    there were too many to read); placeholders are ignored. A number column
    needs a year-like header; text (including numbers written as text) that is
    at least 90 % four-digit years is a year column on its own; text that is at
    least 90 % fiscal-year labels is a fiscal-year column. ``min`` and ``max``
    are the true range; ``values`` is a sorted sample of at most 50.
    """
    if kind == KIND_DATE:
        return {"kind": "date"}
    real = [str(value).strip() for value in values or [] if not is_placeholder(value)]
    if not real:
        return None
    if kind == KIND_NUMERIC and not _YEAR_HEADER.search(header):
        return None
    if kind in (KIND_NUMERIC, KIND_NUMERIC_TEXT, KIND_TEXT):
        years = [year for year in (_year_of(value, kind) for value in real) if year is not None]
        if years and len(years) >= YEAR_SHARE * len(real):
            return _time("year", sorted(set(years)))
    if kind == KIND_TEXT:
        fiscal = [value for value in real if is_fiscal_year(value)]
        if fiscal and len(fiscal) >= FISCAL_YEAR_SHARE * len(real):
            return _time("fiscal_year", sorted(set(fiscal), key=year_sort_key))
    return None


def year_sort_key(label: Any) -> Tuple[int, str]:
    """Order year labels by their first four-digit year, then as written."""
    found = re.search(r"(19|20)\d{2}", str(label))
    return (int(found.group(0)) if found else 0, str(label))


def _time(kind: str, sorted_values: List[Any]) -> Dict[str, Any]:
    return {
        "kind": kind,
        "values": sorted_values[:MAX_TIME_VALUES],
        "min": sorted_values[0],
        "max": sorted_values[-1],
    }


def detect_role(header: str, kind: str, geo: Optional[Dict], time: Optional[Dict]) -> str:
    """The column's role, checked in order: place, time, identifier, measure, dimension."""
    if geo:
        return f"geography_{geo['level']}"
    if time:
        return f"time_{time['kind']}"
    if _IDENTIFIER_HEADER.search(header):
        return ROLE_IDENTIFIER
    if kind in NUMBER_KINDS:
        return ROLE_MEASURE
    return ROLE_DIMENSION


def is_year_header(header: str) -> bool:
    """Whether a header is a year or fiscal year by itself ("2019", "2015-16", "FY 2019-20")."""
    text = re.sub(r"^\s*fy\s*", "", header, flags=re.IGNORECASE)
    return bool(_YEAR.match(text)) or is_fiscal_year(header)


def detect_layout(columns: Sequence[Dict[str, Any]]) -> Tuple[str, List[str]]:
    """``("wide_years", year headers)`` when ≥ 3 number columns are headed by years, else long."""
    year_columns = [
        column["name"]
        for column in columns
        if column.get("kind") in NUMBER_KINDS and is_year_header(column["name"])
    ]
    if len(year_columns) >= WIDE_YEAR_COLUMNS:
        return "wide_years", year_columns
    return "long", []


def not_analysable_reasons(row_count: int, columns: Sequence[Dict[str, Any]]) -> List[str]:
    """Why a table can't be analysed: no rows, or no measure column (empty list: it can)."""
    if row_count == 0:
        return ["empty"]
    if not any(column.get("role") == ROLE_MEASURE for column in columns):
        return ["no_numeric_measure"]
    return []
