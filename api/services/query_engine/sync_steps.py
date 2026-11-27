"""The steps of one ``qe_sync`` pass (the flow is ./sync_pass.py).

- ``PassBudget``: how many tables this pass may still profile, and until when.
- ``find_stale_profiles``: the active tables of a chunk whose stats are missing
  or out of date — no profile yet, a new data table since (a re-upload), an
  older ``PROFILER_VERSION``, or an incomplete profile whose retry time has
  come — leaving out failed ones still in their back-off.
  ``only_resource_id`` narrows to one table (forced).
- ``mark_for_reprofile``: mark every READY profile as due (``--reprofile``,
  after the Geography list is reloaded); passes then work through them.
- ``profile_one``: compute one table's stats and save them if its data table
  hasn't moved meanwhile; a failure is stored as an error code with back-off
  and never stops the other tables.
- ``refresh_facts``: recompute the facts of every table (with READY stats) and
  dataset in a chunk and store the hashes that changed. Run every pass, so
  metadata edits (descriptions, titles, tags, an organisation renamed by a
  bulk update) are picked up without any signal.
- Search index: ``open_search_index`` (create when missing; skip when
  Elasticsearch is down or the vector size changed), ``read_index_states``,
  ``chunk_cards`` + ``plan_index_changes`` (queue new/changed cards first,
  then ones missing a vector, at most QE_DOCS_PER_PASS), ``apply_index_plan``
  (delete documents no longer in the processing set, then write the queue;
  embeddings down → new/changed written without vectors, filled in on a later
  pass). ``write_cards``
  is also what ``--rebuild-index`` uses.

Logs carry ids, counts and error codes only.

Docs: api/views/query_engine/architecture.md
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from uuid import UUID

import structlog
from django.conf import settings
from django.utils import timezone

from api.models import Dataset, Resource, ResourceProfile
from api.models.ResourceProfile import ResourceProfileStatus
from api.services.query_engine.cards import Card, build_cards
from api.services.query_engine.embeddings import (
    EmbeddingsUnavailable,
    embed_texts,
    embeddings_configured,
)
from api.services.query_engine.errors import QueryEngineError
from api.services.query_engine.corpus import processing_set_q
from api.services.query_engine.facts import dataset_facts, facts_hash, resource_facts
from api.services.query_engine.geography_match import GeographyIndex
from api.services.query_engine.profiles import (
    PROFILER_VERSION,
    build_resource_stats,
    dataset_tables,
    record_profile_failure,
    save_resource_profile_if_current,
    write_dataset_facts_hash,
    write_resource_facts_hash,
)
from api.utils.data_tables import error_fields
from search.documents.qe_catalog_document import VECTOR_FIELD
from search.query_engine.index import (
    DocState,
    IndexDimsMismatch,
    SearchIndexError,
    delete_docs,
    ensure_search_index,
    read_doc_states,
    upsert_docs,
)

logger = structlog.get_logger("dataspace.query_engine.sync")

PROFILED = "profiled"
TABLE_MOVED = "table_moved"
FAILED = "failed"


@dataclass
class PassBudget:
    """What one pass may still spend: tables to profile and wall-clock time."""

    profiles_left: int
    deadline: float

    def can_profile(self) -> bool:
        return self.profiles_left > 0 and time.monotonic() < self.deadline

    def seconds_left(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def spend_profile(self) -> None:
        self.profiles_left -= 1


@dataclass
class SyncReport:
    """What a pass did, by count (logged at the end of every pass)."""

    skipped: bool = False
    datasets: int = 0
    marked_for_reprofile: int = 0
    profiles: Dict[str, int] = field(default_factory=dict)
    resource_facts_changed: int = 0
    dataset_facts_changed: int = 0
    index_ready: bool = False
    docs_deleted: int = 0
    docs_upserted: int = 0
    docs_without_vector: int = 0

    def count_profile(self, outcome: str) -> None:
        self.profiles[outcome] = self.profiles.get(outcome, 0) + 1


def _has_table(resource: Resource) -> bool:
    return resource.is_active and getattr(resource, "resourcedatatable", None) is not None


def _is_stale(resource: Resource, now: datetime) -> bool:
    profile: Optional[ResourceProfile] = getattr(resource, "qe_profile", None)
    if profile is None:
        return True
    if profile.data_table_id != resource.resourcedatatable.id:
        return True
    # A retry time (a failure's back-off, an incomplete profile, a re-profile request) decides.
    if profile.retry_after is not None:
        return profile.retry_after <= now
    if profile.status == ResourceProfileStatus.FAILED:
        return True
    return profile.profiler_version != PROFILER_VERSION


def find_stale_profiles(
    datasets: List[Dataset], now: datetime, only_resource_id: Optional[UUID] = None
) -> List[Resource]:
    """The chunk's active tables that need (re)profiling, in dataset and name order."""
    stale: List[Resource] = []
    for dataset in datasets:
        for resource in dataset.resources.all():
            if not _has_table(resource):
                continue
            if only_resource_id is not None:
                if resource.id == only_resource_id:
                    stale.append(resource)
            elif _is_stale(resource, now):
                stale.append(resource)
    return stale


def mark_for_reprofile(now: datetime) -> int:
    """Mark every READY profile in the processing set as due now; returns how many.

    Stored on the profiles (as a retry time), so passes work through all of
    them under their usual limits, however many passes that takes.
    """
    return ResourceProfile.objects.filter(
        status=ResourceProfileStatus.READY,
        resource__dataset__in=Dataset.objects.filter(processing_set_q()),
    ).update(retry_after=now)


def profile_one(
    resource: Resource, geography: GeographyIndex, time_budget_seconds: Optional[float] = None
) -> str:
    """Profile one table and save it if still current.

    Returns "profiled", "table_moved" or "failed:<error code>". After a save,
    the table's facts hash is written straight away, so a summary written for
    the old data stops showing at once.
    """
    data_table_id = resource.resourcedatatable.id
    try:
        stats = build_resource_stats(resource, geography, time_budget_seconds)
    except QueryEngineError as error:
        _store_failure(resource, data_table_id, error.code)
        logger.warning("qe_profile_failed", resource_id=str(resource.id), code=error.code)
        return f"{FAILED}:{error.code}"
    except Exception as error:
        _store_failure(resource, data_table_id, "profile_failed")
        logger.error("qe_profile_failed", resource_id=str(resource.id), **error_fields(error))
        return f"{FAILED}:profile_failed"
    if not save_resource_profile_if_current(resource, data_table_id, stats):
        logger.info("qe_profile_table_moved", resource_id=str(resource.id))
        return TABLE_MOVED
    resource.qe_profile = ResourceProfile.objects.get(resource_id=resource.pk)
    write_resource_facts_hash(resource.qe_profile, facts_hash(resource_facts(resource, stats)))
    return PROFILED


def _store_failure(resource: Resource, data_table_id: UUID, code: str) -> None:
    resource.qe_profile = record_profile_failure(resource, data_table_id, code)


def refresh_facts(datasets: List[Dataset]) -> Dict[str, int]:
    """Recompute and store changed facts hashes for a chunk: ``{"resources": n, "datasets": n}``."""
    changed = {"resources": 0, "datasets": 0}
    for dataset in datasets:
        tables = dataset_tables(dataset)
        for resource, stats in tables:
            if stats is None:
                continue
            new_hash = facts_hash(resource_facts(resource, stats))
            if write_resource_facts_hash(resource.qe_profile, new_hash):
                changed["resources"] += 1
        if write_dataset_facts_hash(dataset, facts_hash(dataset_facts(dataset, tables))):
            changed["datasets"] += 1
    return changed


# --- AI-search index steps (2 and 6-8 of the pass) ---------------------------------


def open_search_index() -> Optional[str]:
    """The live search index, created when missing; None (logged) when it can't be written."""
    try:
        return ensure_search_index(int(settings.QE_EMBEDDINGS_DIMS))
    except IndexDimsMismatch:
        logger.error("qe_sync_index_skipped", reason="vector_size_changed_run_rebuild_index")
        return None
    except SearchIndexError:
        logger.warning("qe_sync_index_skipped", reason="search_unavailable")
        return None


def read_index_states(index: str) -> Optional[Dict[str, DocState]]:
    """Every document's card hash and vector flag; None (logged) when Elasticsearch fails."""
    try:
        return read_doc_states(index)
    except SearchIndexError:
        logger.warning("qe_sync_index_skipped", reason="search_unavailable")
        return None


def chunk_cards(datasets: List[Dataset], sector_slugs: Dict[UUID, List[str]]) -> List[Card]:
    """The search cards of every dataset in a chunk and of its profiled tables."""
    cards: List[Card] = []
    for dataset in datasets:
        cards.extend(build_cards(dataset, dataset_tables(dataset), sector_slugs))
    return cards


@dataclass
class IndexPlan:
    """What the pass will write: every card it built, and the ones that need writing.

    New and changed cards come first; cards that only lack a vector get the
    slots left over, so an embeddings outage can never keep new datasets out
    of the index.
    """

    cap: int
    seen: Set[str] = field(default_factory=set)
    changed: List[Card] = field(default_factory=list)
    missing_vector: List[Card] = field(default_factory=list)
    over_cap: int = 0

    @property
    def refills(self) -> List[Card]:
        """The vector-only cards that fit after the changed ones."""
        return self.missing_vector[: max(0, self.cap - len(self.changed))]

    @property
    def upserts(self) -> List[Card]:
        return self.changed + self.refills


def plan_index_changes(
    plan: IndexPlan, cards: List[Card], states: Dict[str, DocState], embeddings_on: bool
) -> None:
    """Note the chunk's cards; queue new and changed ones first, then ones still missing a vector."""
    for card in cards:
        plan.seen.add(card.doc_id)
        state = states.get(card.doc_id)
        if state is None or state.card_hash != card.card_hash:
            if len(plan.changed) < plan.cap:
                plan.changed.append(card)
            else:
                plan.over_cap += 1
        elif embeddings_on and not state.has_embedding and len(plan.missing_vector) < plan.cap:
            plan.missing_vector.append(card)


def stale_doc_ids(plan: IndexPlan, states: Dict[str, DocState]) -> List[str]:
    """Indexed documents no card was built for this pass (left the processing set, or deleted)."""
    return sorted(doc_id for doc_id in states if doc_id not in plan.seen)


def doc_body(card: Card, vector: Optional[List[float]]) -> Dict[str, Any]:
    """The document written for a card, with its vector when there is one."""
    body: Dict[str, Any] = {
        **card.fields,
        "has_embedding": vector is not None,
        "embedding_model": settings.QE_EMBEDDINGS_MODEL if vector is not None else None,
        "indexed_at": timezone.now().isoformat(),
    }
    if vector is not None:
        body[VECTOR_FIELD] = vector
    return body


def write_cards(index: str, cards: List[Card], refills: Sequence[Card] = ()) -> Tuple[int, int]:
    """Embed and write cards: (written, written without a vector). Raises SearchIndexError.

    ``refills`` are cards already indexed without a vector, written again only
    if they now get one. When the embeddings service fails, ``cards`` are
    written without vectors (still found by keywords) and get their vectors on
    a later pass; ``refills`` are left as they are.
    """
    batch = list(cards) + list(refills)
    if not batch:
        return 0, 0
    vectors: List[Optional[List[float]]]
    if not embeddings_configured():
        # No embeddings service set up: keyword-only documents, without calling anyone.
        batch = list(cards)
        vectors = [None] * len(batch)
    else:
        try:
            vectors = list(embed_texts([card.text for card in batch]))
        except EmbeddingsUnavailable:
            batch = list(cards)
            vectors = [None] * len(batch)
    written = upsert_docs(index, [(c.doc_id, doc_body(c, v)) for c, v in zip(batch, vectors)])
    return written, sum(1 for v in vectors if v is None)


def apply_index_plan(index: str, plan: IndexPlan, states: Dict[str, DocState]) -> Dict[str, int]:
    """Delete stale documents, then write the queued cards; Elasticsearch failing mid-way is logged."""
    done = {"deleted": 0, "upserted": 0, "without_vector": 0}
    try:
        done["deleted"] = delete_docs(index, stale_doc_ids(plan, states))
        done["upserted"], done["without_vector"] = write_cards(index, plan.changed, plan.refills)
    except SearchIndexError:
        logger.warning("qe_sync_index_write_failed", **done)
    if plan.over_cap:
        logger.info("qe_sync_docs_left_for_next_pass", count=plan.over_cap)
    return done
