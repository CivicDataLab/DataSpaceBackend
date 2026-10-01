"""Bridge between the deployment's *metadata definitions* and the crosswalk.

Administrators define extra dataset fields in Django admin (``Metadata``:
label, URN, data type, required or optional). Publishers fill them in the
edit form and the values live in ``DatasetMetadata``. Until now those values
were opaque strings: the import could not prefill them and the export could
not place them in a standard.

This module gives each definition a *crosswalk concept* so both sides can use
it. A definition is matched, in order, by

1. its URN, once normalised: prefix dropped, camelCase to snake_case, so
   ``ds:source_website``, ``dcterms:source`` and ``schema:sourceWebsite`` all
   become ``source_website`` / ``source``;
2. any property name a standard uses for a concept in the contract
   (``dcterms:issued`` -> ``issued``, ``dcat:landingPage`` -> ``landing_page``);
3. its label, normalised the same way ("Date of Creation of Dataset" ->
   ``date_of_creation_of_dataset`` -> ``created``).

Anything that resolves to nothing stays an opaque string: the import leaves
it for the publisher and the export lists it under ``dropped`` in the report,
so the gap is visible instead of silently lost.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from api.models import Dataset, Metadata
    from api.services.platform_importers.base import PlatformDatasetInfo

# House names and standard names that all mean the same crosswalk concept.
# Keys are normalised (see ``normalise``); values are concept keys in
# contracts/crosswalk.json, plus ``citation`` which the contract does not
# carry yet but Croissant (citeAs) does.
ALIASES: Dict[str, str] = {
    # where the dataset came from
    "source": "source",
    "source_url": "source",
    "source_website": "source",
    "source_link": "source",
    "original_source": "source",
    "original_url": "source",
    "data_source": "source",
    "was_derived_from": "source",
    "source_identifier": "source_identifier",
    "source_id": "source_identifier",
    "source_platform": "source_platform",
    "imported_from": "source_platform",
    # people and organisations
    "author": "creator",
    "creator": "creator",
    "authors": "creator",
    "original_author": "creator",
    "publisher": "publisher",
    # dates
    "created": "created",
    "created_on": "created",
    "created_at": "created",
    "creation_date": "created",
    "date_created": "created",
    "date_of_creation": "created",
    "date_of_creation_of_dataset": "created",
    "issued": "issued",
    "published": "issued",
    "published_on": "issued",
    "date_published": "issued",
    "release_date": "issued",
    "modified": "modified",
    "last_modified": "modified",
    "last_updated": "modified",
    "updated": "modified",
    "updated_on": "modified",
    "date_modified": "modified",
    "source_last_updated": "modified",
    # rights and identity
    "license": "license",
    "licence": "license",
    "original_license": "license",
    "source_license": "license",
    "rights": "rights",
    "version": "version",
    "revision": "version",
    # links and text
    "homepage": "homepage",
    "home_page": "homepage",
    "website": "homepage",
    "project_url": "homepage",
    "landing_page": "landing_page",
    "citation": "citation",
    "cite_as": "citation",
    "how_to_cite": "citation",
    "language": "language",
    "languages": "language",
    "in_language": "language",
    # coverage and cadence
    "temporal_coverage_start": "temporal_coverage_start",
    "temporal_start": "temporal_coverage_start",
    "period_start": "temporal_coverage_start",
    "start_date": "temporal_coverage_start",
    "coverage_start": "temporal_coverage_start",
    "temporal_coverage_end": "temporal_coverage_end",
    "temporal_end": "temporal_coverage_end",
    "period_end": "temporal_coverage_end",
    "end_date": "temporal_coverage_end",
    "coverage_end": "temporal_coverage_end",
    "accrual_periodicity": "accrual_periodicity",
    "frequency": "accrual_periodicity",
    "update_frequency": "accrual_periodicity",
    "periodicity": "accrual_periodicity",
}

# Concepts whose value is a calendar date on the way in and out.
DATE_CONCEPTS = {
    "created",
    "issued",
    "modified",
    "temporal_coverage_start",
    "temporal_coverage_end",
}
# Concepts whose value is a list joined with commas in the definition's cell.
LIST_CONCEPTS = {"language"}

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalise(name: Optional[str]) -> str:
    """``ds:createdOn`` -> ``created_on``; ``Source Website`` -> ``source_website``."""
    if not name:
        return ""
    local = name.strip().rsplit(":", 1)[-1].rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    local = _CAMEL.sub("_", local)
    return _NON_WORD.sub("_", local.lower()).strip("_")


@lru_cache(maxsize=1)
def _contract_property_index() -> Dict[str, str]:
    """Normalised standard property name -> concept, from the vendored contract."""
    from api.services.metadata_export.crosswalk import Crosswalk

    index: Dict[str, str] = {}
    for std in Crosswalk.load().standards.values():
        # ``export`` is a flat list of entries; ``import`` is nested
        # node -> property -> [entries].
        entries: List[dict] = list(std.get("export") or [])
        for node, by_property in (std.get("import") or {}).items():
            for prop, found in by_property.items():
                for entry in found if isinstance(found, list) else [found]:
                    entries.append(dict(entry, property=entry.get("property") or prop, node=node))
        for entry in entries:
            prop, concept = entry.get("property"), entry.get("concept")
            if prop and concept and entry.get("node", "dataset") == "dataset":
                index.setdefault(normalise(prop), concept)
    return index


def concept_for(urn: Optional[str], label: Optional[str] = None) -> Optional[str]:
    """The crosswalk concept a definition stands for, or None if unrecognised."""
    for candidate in (normalise(urn), normalise(label)):
        if not candidate:
            continue
        if candidate in ALIASES:
            return ALIASES[candidate]
        concept = _contract_property_index().get(candidate)
        if concept:
            return concept
    return None


# --------------------------------------------------------------------- import
def platform_values(info: "PlatformDatasetInfo", platform_label: str) -> Dict[str, str]:
    """What an import can offer each concept, as the string a definition cell holds."""

    def day(value: Optional[datetime]) -> str:
        return value.date().isoformat() if value else ""

    values = {
        "source": info.source_url,
        "source_identifier": info.identifier,
        "source_platform": platform_label,
        "creator": info.author,
        "publisher": info.author,
        "created": day(info.created_at),
        "issued": day(info.created_at),
        "modified": day(info.last_updated),
        "license": info.license,
        "version": info.revision,
        "homepage": info.homepage,
        "citation": info.citation,
        "language": ", ".join(info.languages or []),
    }
    return {k: v for k, v in values.items() if v}


# --------------------------------------------------------------------- export
def _coerce(concept: str, raw: str) -> Any:
    value = (raw or "").strip()
    if not value:
        return None
    if concept in LIST_CONCEPTS:
        return [v.strip() for v in value.split(",") if v.strip()]
    if concept in DATE_CONCEPTS:
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            return value
    return value


def definition_values(dataset: "Dataset") -> Tuple[Dict[str, Any], List[dict]]:
    """Definition-backed values of a dataset, keyed by concept.

    Returns ``(values, unmapped)``. ``unmapped`` lists definitions the mapping
    could not place, for the export report.
    """
    values: Dict[str, Any] = {}
    unmapped: List[dict] = []
    rows = dataset.metadata.select_related("metadata_item").all()
    for row in rows:
        item: "Metadata" = row.metadata_item
        if not item.enabled:
            continue
        concept = concept_for(item.urn, item.label)
        if concept is None:
            unmapped.append({"label": item.label, "urn": item.urn, "value": row.value})
            continue
        coerced = _coerce(concept, row.value)
        if coerced in (None, "", []):
            continue
        values.setdefault(concept, coerced)
    return values, unmapped
