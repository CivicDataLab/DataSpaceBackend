"""Resolve the platform's labels to URIs using the vendored value lists.

The standards want identifiers, not names: ``dcterms:spatial "Assam"`` is not
a spatial reference. The lists under ``contracts/`` (see contracts/README.md
repo's value superset) give a URI per licence, sector and geography. Anything
they do not know is returned as a plain label so the crosswalk reports it as
unresolved instead of silently emitting a bad value.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

CONTRACTS = Path(__file__).resolve().parent / "contracts"


def _rows(name: str) -> List[Dict[str, str]]:
    with open(CONTRACTS / name, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _alt_codes(raw: str) -> Dict[str, str]:
    """Parse the CSV's 'k=v|k=v' alt_codes column (';' tolerated too)."""
    out: Dict[str, str] = {}
    for part in (raw or "").replace(";", "|").split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


@lru_cache(maxsize=1)
def _license_index() -> Dict[str, str]:
    """Lower-cased key / label / DataSpace enum / SPDX id -> URI."""
    index: Dict[str, str] = {}
    for r in _rows("licenses.csv"):
        uri = r.get("uri") or ""
        if not uri:
            continue
        for k in (r.get("key"), r.get("label"), r.get("code")):
            if k:
                index[k.strip().lower()] = uri
        alt = _alt_codes(r.get("alt_codes", ""))
        for k in ("dataspace_enum", "spdx", "spdx_id", "authority_label"):
            if alt.get(k):
                index[alt[k].strip().lower()] = uri
    return index


@lru_cache(maxsize=1)
def _sector_index() -> Dict[str, str]:
    index: Dict[str, str] = {}
    for r in _rows("sectors.csv"):
        uri = r.get("uri") or ""
        if not uri:
            continue
        for k in (r.get("key"), r.get("label"), r.get("code")):
            if k:
                index[k.strip().lower()] = uri
        key = r.get("key") or ""
        if ":" in key:  # "cdl:child-rights" -> "child-rights"
            index[key.split(":", 1)[1].lower()] = uri
    return index


@lru_cache(maxsize=1)
def _geography_index() -> Dict[str, Dict[str, str]]:
    """label(lower) -> {tier -> uri}; tier disambiguates 'Aurangabad' etc."""
    index: Dict[str, Dict[str, str]] = {}
    for r in _rows("geographies.csv"):
        uri, label, tier = (
            r.get("uri") or "",
            (r.get("label") or "").strip().lower(),
            (r.get("tier") or "").upper(),
        )
        if uri and label:
            index.setdefault(label, {})[tier] = uri
    return index


def license_uri(value: Optional[str]) -> Optional[str]:
    return _license_index().get((value or "").strip().lower())


def sector_uri(name: Optional[str]) -> Optional[str]:
    return _sector_index().get((name or "").strip().lower())


def geography_uri(name: Optional[str], geo_type: Optional[str] = None) -> Optional[str]:
    tiers = _geography_index().get((name or "").strip().lower())
    if not tiers:
        return None
    if geo_type and geo_type.upper() in tiers:
        return tiers[geo_type.upper()]
    # Prefer the coarsest match when the platform did not say which level.
    for tier in ("COUNTRY", "REGION", "STATE", "UT", "DISTRICT"):
        if tier in tiers:
            return tiers[tier]
    return next(iter(tiers.values()))


def concept(name: str, uri: Optional[str]) -> Dict[str, str]:
    """Shape the crosswalk renders: uri when known, else the bare name (reported)."""
    return {"name": name, "uri": uri} if uri else {"name": name}
