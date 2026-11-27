"""The AI-search documents ("cards") for a dataset and its tables.

Every corpus dataset gets a dataset card from its metadata and tables (so
PDF- or API-only datasets stay findable); every table with a READY profile
gets its own card. A card holds the fields the search index filters and
ranks on (title, search text, sectors with their parent sectors, places,
year range, place level, analysable) and the text that gets embedded.
Summaries go in only while they are current.

``card_hash`` covers every field plus CARD_VERSION and the embedding model's
fingerprint, so a changed description, tag, summary, stat or embedding
model re-indexes the card, and nothing else does.

Pure: works on objects the sync pass already loaded.

Docs: api/views/query_engine/architecture.md
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import UUID

from django.conf import settings

from api.models import Dataset, Resource
from api.services.query_engine.embeddings import model_fingerprint
from api.services.query_engine.facts import column_descriptions, dataset_facts, dataset_metadata
from api.services.query_engine.profile_overlay import column_unit, coverage, coverage_text
from api.services.query_engine.profile_views import current_summary

CARD_VERSION = 1
MAX_SEARCH_TEXT_CHARS = 20_000
MAX_TOP_VALUES_PER_COLUMN = 10
_YEAR = re.compile(r"(19|20)\d{2}")
_FISCAL_END = re.compile(r"(19|20)(\d{2})\s*[-–/]\s*(\d{2,4})")


@dataclass(frozen=True)
class Card:
    """One search document: its id, its fields, the text to embed, and its hash."""

    doc_id: str
    fields: Dict[str, Any]
    text: str
    card_hash: str


def dataset_doc_id(dataset_id: Any) -> str:
    return f"d:{dataset_id}"


def resource_doc_id(resource_id: Any) -> str:
    return f"r:{resource_id}"


def year_range(labels: Iterable[Any]) -> Tuple[Optional[int], Optional[int]]:
    """First and last calendar year covered by year labels ("2015", "2015-16" ends in 2016)."""
    starts: List[int] = []
    ends: List[int] = []
    for label in labels:
        if label is None:
            continue
        text = str(label)
        found = _YEAR.search(text)
        if not found:
            continue
        start = int(found.group(0))
        fiscal = _FISCAL_END.search(text)
        starts.append(start)
        ends.append(start + 1 if fiscal else start)
    return (min(starts), max(ends)) if starts else (None, None)


def _finish(doc_id: str, fields: Dict[str, Any]) -> Card:
    fields["search_text"] = fields["search_text"][:MAX_SEARCH_TEXT_CHARS]
    text = "\n".join(part for part in (fields["title"], fields["search_text"]) if part)
    fields["rerank_text"] = text[: int(settings.QE_RERANK_DOC_CHARS)]
    canonical = json.dumps(fields, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(
        f"{canonical}|{CARD_VERSION}|{model_fingerprint()}".encode("utf-8")
    ).hexdigest()
    return Card(doc_id=doc_id, fields={**fields, "card_hash": digest}, text=text, card_hash=digest)


def _lines(*parts: Any) -> str:
    out: List[str] = []
    for part in parts:
        if isinstance(part, (list, tuple)):
            out.extend(str(p) for p in part if p)
        elif part:
            out.append(str(part))
    return "\n".join(out)


def _places(stats: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for column in stats.get("columns", []):
        geo = column.get("geo") or {}
        names.extend(geo.get("matched", []))
        names.extend(geo.get("parent_states", []))
    return names


def _table_lines(resource: Resource, stats: Dict[str, Any]) -> List[str]:
    descriptions = column_descriptions(resource)
    lines: List[str] = []
    for column in stats.get("columns", []):
        name = column["name"]
        unit = column_unit(name, descriptions.get(name))
        label = " — ".join(part for part in (name, descriptions.get(name), unit) if part)
        lines.append(label)
        if column.get("role") in ("dimension", "geography_state", "geography_district"):
            top = column.get("top_values") or []
            lines.extend(str(value) for value, _ in top[:MAX_TOP_VALUES_PER_COLUMN])
    return lines


def build_cards(
    dataset: Dataset,
    tables: Sequence[Tuple[Resource, Optional[Dict[str, Any]]]],
    sector_slugs: Dict[UUID, List[str]],
) -> List[Card]:
    """The dataset's card, then one card per table with READY stats.

    ``sector_slugs`` maps each sector to its slug and its parents' slugs.
    """
    metadata = dataset_metadata(dataset)
    slugs = sorted({slug for s in dataset.sectors.all() for slug in sector_slugs.get(s.id, [])})
    organization_id = str(dataset.organization_id) if dataset.organization_id else None
    dataset_summary = current_summary(getattr(dataset, "qe_profile", None))
    facts = dataset_facts(dataset, tables)

    table_places: List[str] = []
    for _, stats in tables:
        if stats:
            table_places.extend(_places(stats))
    union = facts["coverage"]
    year_min, year_max = year_range([union["year_min"], union["year_max"]])
    cards = [
        _finish(
            dataset_doc_id(dataset.id),
            {
                "doc_kind": "dataset",
                "dataset_id": str(dataset.id),
                "resource_id": None,
                "organization_id": organization_id,
                "title": metadata["title"],
                "search_text": _lines(
                    metadata["description"],
                    metadata["organization"],
                    metadata["sectors"],
                    metadata["tags"],
                    metadata["places"],
                    [f"{t['name']}: {t['coverage_text']}" for t in facts["tables"]],
                    [o["name"] for o in facts["other_resources"]],
                    facts["coverage_text"],
                    dataset_summary["text"] if dataset_summary else None,
                ),
                "summary": dataset_summary["text"] if dataset_summary else None,
                "sectors": slugs,
                "geographies": sorted(set(metadata["places"]) | set(table_places)),
                "year_min": year_min,
                "year_max": year_max,
                "geo_level": union["geo_level"],
                "analysable": any(t["analysable"] for t in facts["tables"]),
            },
        )
    ]

    for resource, stats in tables:
        if not stats:
            continue
        found = coverage(stats)
        table_min, table_max = year_range([found["year_min"], found["year_max"]])
        summary = current_summary(getattr(resource, "qe_profile", None))
        cards.append(
            _finish(
                resource_doc_id(resource.id),
                {
                    "doc_kind": "resource",
                    "dataset_id": str(dataset.id),
                    "resource_id": str(resource.id),
                    "organization_id": organization_id,
                    "title": f"{resource.name} — {metadata['title']}",
                    "search_text": _lines(
                        resource.description,
                        metadata["description"],
                        metadata["organization"],
                        metadata["sectors"],
                        metadata["tags"],
                        metadata["places"],
                        _table_lines(resource, stats),
                        coverage_text(found),
                        summary["text"] if summary else None,
                    ),
                    "summary": summary["text"] if summary else None,
                    "sectors": slugs,
                    "geographies": sorted(set(metadata["places"]) | set(_places(stats))),
                    "year_min": table_min,
                    "year_max": table_max,
                    "geo_level": found["geo_level"],
                    "analysable": bool(stats.get("analysable")),
                },
            )
        )
    return cards
