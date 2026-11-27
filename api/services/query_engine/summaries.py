"""Which profiles need a model-written summary, and storing one safely.

The query engine pulls work and pushes results; the backend owns storage and checks.

- ``pending_summaries``: up to ``limit`` items (oldest change first) that need
  a summary — ``summary_needed``, fewer than 2 rejections for the current
  facts, in the corpus and the processing set. Tables need a READY profile
  for their current data; a dataset is offered only once all its active
  tables are READY. All of that is decided in the database. Each
  item carries the facts the backend computes now (cut to 8,000 characters of
  JSON: long quirk lists shortened, the list of non-table files cut to 5,
  then columns or tables dropped from the end, each with a count of what was
  left out) and their hash.
- ``get_summary_target``: the profile a write is for, only while its dataset
  (and table) is still in the corpus — else NotFound.
- ``current_facts``: the facts recomputed from stored stats and metadata,
  never taken from the caller; ``require_same_facts`` refuses (409) a summary
  written from other facts.
- ``save_summary_if_current`` and ``record_rejection`` are single conditional
  UPDATEs on the facts hash the summary was written from, so a sync pass
  writing newer facts in between wins: nothing is stored and the item stays
  needed for its new facts.

Query shape: ``filter(summary_needed=True, summary_rejections__lt=2).order_by("modified")``
on each profile table, riding the partial index on ``modified WHERE summary_needed``.

Docs: api/views/query_engine/architecture.md
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

import structlog
from django.db.models import F, Prefetch
from django.utils import timezone

from api.models import Dataset, DatasetProfile, Resource, ResourceProfile, ResourceSchema
from api.models.ResourceProfile import ResourceProfileStatus
from api.services.query_engine.corpus import analysable_resource_q, processing_set_q
from api.services.query_engine.errors import FactsChanged, NotFound
from api.services.query_engine.facts import dataset_facts, facts_hash, resource_facts
from api.services.query_engine.profiles import load_dataset_tables, ready_stats
from api.services.query_engine.summary_check import facts_text_size
from api.utils.dataset_access import public_published_datasets_q

logger = structlog.get_logger("dataspace.query_engine.summaries")

MAX_REJECTIONS = 2
MAX_PENDING = 20
MAX_FACTS_CHARS = 8000
# How many candidates per level one pending call may read past skipped ones.
MAX_SCANNED = 200
MAX_QUIRK_COLUMNS = 10
# Non-table files are cut down to this many before any table is dropped.
MIN_KEPT_ITEMS = 5
RESOURCE = "resource"
DATASET = "dataset"

Profile = Union[ResourceProfile, DatasetProfile]


@dataclass
class SummaryTarget:
    """What a summary is for: its level, its profile, and the dataset or table it describes."""

    level: str
    profile: Profile
    dataset: Dataset
    resource: Optional[Resource] = None


def _load_resource(resource_id: Any) -> Optional[Resource]:
    found = (
        Resource.objects.select_related("dataset__organization", "resourcedatatable", "qe_profile")
        .prefetch_related(
            Prefetch("resourceschema_set", queryset=ResourceSchema.objects.order_by("id")),
            "dataset__tags",
            "dataset__sectors",
            "dataset__geographies",
        )
        .filter(analysable_resource_q(), pk=resource_id)
        .first()
    )
    return found


def _load_dataset(dataset_id: Any) -> Optional[Dataset]:
    return (
        Dataset.objects.select_related("organization", "qe_profile")
        .filter(public_published_datasets_q(), pk=dataset_id)
        .first()
    )


def get_summary_target(level: str, item_id: UUID) -> SummaryTarget:
    """The profile a summary is for, while it is in the corpus and READY; else NotFound (404)."""
    if level == RESOURCE:
        resource = _load_resource(item_id)
        if resource is not None and ready_stats(resource) is not None:
            return SummaryTarget(RESOURCE, resource.qe_profile, resource.dataset, resource)
    elif level == DATASET:
        dataset = _load_dataset(item_id)
        profile = getattr(dataset, "qe_profile", None) if dataset is not None else None
        if dataset is not None and profile is not None:
            return SummaryTarget(DATASET, profile, dataset)
    raise NotFound(reason="summary_target_not_found", level=level, item_id=str(item_id))


def current_facts(target: SummaryTarget) -> Dict[str, Any]:
    """The target's facts, recomputed now from stored stats and metadata."""
    if target.level == RESOURCE and target.resource is not None:
        return resource_facts(target.resource, ready_stats(target.resource) or {})
    return dataset_facts(target.dataset, load_dataset_tables(target.dataset))


def require_same_facts(target: SummaryTarget, facts: Dict[str, Any], written_from: str) -> None:
    """Refuse (409) a summary written from facts other than the current ones."""
    current = facts_hash(facts)
    if written_from != current or target.profile.facts_hash != current:
        raise FactsChanged(reason="facts_changed", level=target.level)


def _model(level: str) -> Any:
    return ResourceProfile if level == RESOURCE else DatasetProfile


def save_summary_if_current(
    target: SummaryTarget, written_from: str, text: str, model: str, prompt_version: str
) -> bool:
    """Store the summary only if the facts hash is still the one it was written from."""
    updated = (
        _model(target.level)
        .objects.filter(pk=target.profile.pk, facts_hash=written_from)
        .update(
            summary_text=text,
            summary_facts_hash=written_from,
            summary_model=model,
            summary_prompt_version=prompt_version,
            summary_generated_at=timezone.now(),
            summary_needed=False,
        )
    )
    return bool(updated)


def record_rejection(target: SummaryTarget, written_from: str) -> None:
    """Count a refused summary against the facts it was written from (only while they are current)."""
    _model(target.level).objects.filter(pk=target.profile.pk, facts_hash=written_from).update(
        summary_rejections=F("summary_rejections") + 1
    )


def _short_quirks(quirks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    shortened = []
    for quirk in quirks:
        columns = quirk.get("columns", [])
        if len(columns) > MAX_QUIRK_COLUMNS:
            quirk = {
                **quirk,
                "columns": columns[:MAX_QUIRK_COLUMNS],
                "columns_omitted": len(columns) - MAX_QUIRK_COLUMNS,
            }
        shortened.append(quirk)
    return shortened


def _fit_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    trimmed = dict(facts)
    # Quirks name their columns; long lists say how many instead.
    if "quirks" in trimmed:
        trimmed["quirks"] = _short_quirks(trimmed["quirks"])
    if "other_resources" in trimmed:
        trimmed = _trim_list(trimmed, "other_resources", keep=MIN_KEPT_ITEMS)
    key = "columns" if "columns" in trimmed else "tables"
    return _trim_list(trimmed, key, keep=0)


def _trim_list(facts: Dict[str, Any], key: str, keep: int) -> Dict[str, Any]:
    """Drop entries from the end of ``facts[key]`` (keeping ``keep``) until within the cap."""
    trimmed = dict(facts)
    items = list(trimmed.get(key, []))
    omitted = 0
    while len(items) > keep and facts_text_size({**trimmed, key: items}) > MAX_FACTS_CHARS:
        items.pop()
        omitted += 1
    trimmed[key] = items
    if omitted:
        trimmed[f"{key}_omitted"] = omitted
    return trimmed


def _pending_resources() -> Any:
    """Tables needing a summary: READY for their current data, in the processing set (oldest first)."""
    return (
        ResourceProfile.objects.filter(
            summary_needed=True,
            summary_rejections__lt=MAX_REJECTIONS,
            status=ResourceProfileStatus.READY,
            data_table_id=F("resource__resourcedatatable__id"),
            resource__dataset__in=Dataset.objects.filter(processing_set_q()),
        )
        .filter(analysable_resource_q("resource__"))
        .exclude(facts_hash="")
        .order_by("modified", "pk")
        .values_list("resource_id", "modified")
    )


def _pending_datasets() -> Any:
    """Datasets needing a summary whose active tables are all READY, in the processing set."""
    not_ready = Resource.objects.filter(is_active=True, resourcedatatable__isnull=False).exclude(
        qe_profile__status=ResourceProfileStatus.READY,
        qe_profile__data_table_id=F("resourcedatatable__id"),
    )
    return (
        DatasetProfile.objects.filter(
            summary_needed=True,
            summary_rejections__lt=MAX_REJECTIONS,
            dataset__in=Dataset.objects.filter(processing_set_q()),
        )
        .exclude(facts_hash="")
        .exclude(dataset_id__in=not_ready.values("dataset_id"))
        .order_by("modified", "pk")
        .values_list("dataset_id", "modified")
    )


def pending_summaries(limit: int) -> List[Dict[str, Any]]:
    """Items that need a summary now, oldest change first: ``[{level, id, facts_hash, facts}]``.

    Eligibility (corpus, processing set, readiness, rejections) is decided in
    the database, so items that can't be offered never fill the batch. Items
    whose stored facts are behind (the next sync pass rewrites them) are
    skipped and the scan reads on, up to MAX_SCANNED candidates; skips are logged.
    """
    limit = max(1, min(int(limit), MAX_PENDING))
    candidates = sorted(
        [(m, RESOURCE, i) for i, m in _pending_resources()[:MAX_SCANNED]]
        + [(m, DATASET, i) for i, m in _pending_datasets()[:MAX_SCANNED]],
        key=lambda candidate: (candidate[0], candidate[1], str(candidate[2])),
    )
    items: List[Dict[str, Any]] = []
    skipped = 0
    for _, level, item_id in candidates:
        if len(items) >= limit:
            break
        item = _pending_item(level, item_id)
        if item is None:
            skipped += 1
        else:
            items.append(item)
    if skipped:
        logger.info("qe_summaries_pending_skipped", skipped=skipped, offered=len(items))
    return items


def _pending_item(level: str, item_id: Any) -> Optional[Dict[str, Any]]:
    try:
        target = get_summary_target(level, item_id)
    except NotFound:
        return None
    facts = current_facts(target)
    if facts_hash(facts) != target.profile.facts_hash:
        return None  # the next sync pass writes the new hash first
    return {
        "level": level,
        "id": str(item_id),
        "facts_hash": target.profile.facts_hash,
        "facts": _fit_facts(facts),
    }
