"""Recognising place columns: which values are Indian states or districts we know.

``load_geography_index`` reads the Geography table once (one query) into
normalised name lookups; ``match_places`` checks one text column's distinct
values against it. Names are compared after lower-casing, collapsing spaces
and dropping a trailing "district" / "dist." ("Kamrup District" = "Kamrup").

A column is a district (or state) column when its header says so (district,
dist., zila, जिला / state, UT, राज्य) and at least 20 % of its distinct values
are such names, or, whatever its header, when at least 60 % are. Total rows
and placeholders are left out of the share. The result carries the match share, up to 10 unmatched values with the
closest known name (for spelling variants such as "Kamrup Metro" →
"Kamrup Metropolitan"), the states the matched districts belong to, and the matched names
themselves (for search filters on places).

Docs: api/views/query_engine/architecture.md
"""

import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from api.models import Geography
from api.services.query_engine.column_roles import is_placeholder, is_total_marker
from api.utils.enums import GeoTypes

MATCH_SHARE = 0.6
# A header that names a place ("District") still needs this share of known names,
# so a "District code" column of codes stays an identifier.
HEADER_MATCH_SHARE = 0.2
MAX_UNMATCHED = 10
MAX_MATCHED = 1000
CLOSEST_CUTOFF = 0.6

_STATE_TYPES = {GeoTypes.STATE.value, GeoTypes.UT.value}
_DISTRICT_HEADER = re.compile(r"(^|[^a-z])(district|dist\.?|zila|zilla)([^a-z]|$)|जिला|ज़िला", re.I)
_STATE_HEADER = re.compile(r"(^|[^a-z])(state|states|ut|union territory)([^a-z]|$)|राज्य", re.I)
_TRAILING_DISTRICT = re.compile(r"\s+(district|dist\.?)$")


@dataclass
class GeographyIndex:
    """Known state and district names by normalised name, and each district's state."""

    states: Dict[str, str] = field(default_factory=dict)
    districts: Dict[str, str] = field(default_factory=dict)
    state_of_district: Dict[str, str] = field(default_factory=dict)


def normalise_place(value: str) -> str:
    """Lower-case, single spaces, no trailing "district"."""
    cleaned = " ".join(str(value).lower().split())
    return _TRAILING_DISTRICT.sub("", cleaned)


def load_geography_index() -> GeographyIndex:
    """Every state, union territory and district name we know, in one query."""
    index = GeographyIndex()
    rows = Geography.objects.values_list("name", "type", "parent_id__name")
    for name, geo_type, parent_name in rows:
        key = normalise_place(name)
        if geo_type in _STATE_TYPES:
            index.states[key] = name
        elif geo_type == GeoTypes.DISTRICT.value:
            index.districts[key] = name
            if parent_name:
                index.state_of_district[name] = parent_name
    return index


def match_places(header: str, values: Sequence[str], index: GeographyIndex) -> Optional[Dict]:
    """The place level of a text column and how well its values match, or None if not a place column."""
    candidates = sorted(
        {v for v in values if v.strip() and not is_total_marker(v) and not is_placeholder(v)}
    )
    header_level = _header_level(header)
    shares = {
        "district": _share(candidates, index.districts),
        "state": _share(candidates, index.states),
    }
    level = header_level or max(shares, key=lambda name: shares[name])
    needed = HEADER_MATCH_SHARE if header_level else MATCH_SHARE
    if shares[level] < needed:
        return None
    if not candidates:
        return None
    known = index.districts if level == "district" else index.states
    matched = [
        known[normalise_place(value)] for value in candidates if normalise_place(value) in known
    ]
    unmatched = [value for value in candidates if normalise_place(value) not in known]
    return {
        "level": level,
        "match_pct": round(100.0 * len(matched) / len(candidates), 1),
        "unmatched": [
            {"value": value, "closest": _closest(value, known)}
            for value in unmatched[:MAX_UNMATCHED]
        ],
        "parent_states": (
            sorted(
                {
                    index.state_of_district[name]
                    for name in matched
                    if name in index.state_of_district
                }
            )
            if level == "district"
            else []
        ),
        "matched": sorted(set(matched))[:MAX_MATCHED],
        "matched_count": len(set(matched)),
    }


def _header_level(header: str) -> Optional[str]:
    if _DISTRICT_HEADER.search(header):
        return "district"
    if _STATE_HEADER.search(header):
        return "state"
    return None


def _share(values: List[str], known: Dict[str, str]) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if normalise_place(value) in known) / len(values)


def _closest(value: str, known: Dict[str, str]) -> Optional[str]:
    found = difflib.get_close_matches(
        normalise_place(value), list(known), n=1, cutoff=CLOSEST_CUTOFF
    )
    return known[found[0]] if found else None
