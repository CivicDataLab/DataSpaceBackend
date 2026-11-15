"""Which datasets and tables the query engine may see, as database filters.

- **Corpus**: published, public, data-type datasets (``public_published_datasets_q``).
- **Analysable resource**: an active resource of a corpus dataset that has a
  data table (a ResourceDataTable row). PDFs, link-only imports and failed
  uploads have none.
- **Platform scope**: the corpus, narrowed to the sectors in
  ``QE_PLATFORM_SECTORS`` and their sub-sectors when that setting is set.
- **Collaborative scope**: the corpus datasets attached to one published
  collaborative (resolved in ./scope.py). A collaborative only narrows the
  corpus; a private dataset attached to it stays out.
- **Processing set**: what ``qe_sync`` profiles and indexes — platform scope
  plus the corpus datasets of every enabled, published collaborative.

Every endpoint re-checks membership here on every call, so a sync pass that
lags can only make results stale, never leak them. A refusal is ``NotFound``
(404), logged with ids and a reason code, never saying whether the item exists.

Query shapes: one-row lookups ride primary keys; membership uses the
dataset-sector and collaborative-dataset through tables (unique pairs);
sector descendants are resolved in Python from the small sector table.

Docs: api/views/query_engine/architecture.md
"""

from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    FrozenSet,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
)
from uuid import UUID

from django.conf import settings
from django.db.models import Prefetch, Q

from api.models import Collaborative, Dataset, Resource, ResourceSchema, Sector
from api.services.query_engine.errors import NotFound
from api.utils.dataset_access import public_published_datasets_q
from api.utils.enums import CollaborativeStatus

if TYPE_CHECKING:
    from api.services.query_engine.scope import ResolvedScope

CORPUS_CHUNK_SIZE = 200

T = TypeVar("T")


def analysable_resource_q(prefix: str = "") -> Q:
    """Active resources of corpus datasets that have a data table. ``prefix`` reaches the resource."""
    return Q(
        **{f"{prefix}is_active": True, f"{prefix}resourcedatatable__isnull": False}
    ) & public_published_datasets_q(f"{prefix}dataset__")


def platform_sector_ids() -> Optional[FrozenSet[UUID]]:
    """The ids of the configured platform sectors and all their sub-sectors (None: no narrowing).

    One query over the sector table. A configured slug that matches no sector
    narrows to nothing rather than widening to everything.
    """
    slugs = set(settings.QE_PLATFORM_SECTORS)
    if not slugs:
        return None
    rows = list(Sector.objects.values_list("id", "slug", "parent_id"))
    children: Dict[Optional[UUID], List[UUID]] = {}
    for sector_id, _, parent_id in rows:
        children.setdefault(parent_id, []).append(sector_id)
    found: Set[UUID] = set()
    pending = [sector_id for sector_id, slug, _ in rows if slug in slugs]
    while pending:
        sector_id = pending.pop()
        if sector_id not in found:
            found.add(sector_id)
            pending.extend(children.get(sector_id, []))
    return frozenset(found)


def _in_sectors_q(sector_ids: FrozenSet[UUID], prefix: str) -> Q:
    members = Dataset.sectors.through.objects.filter(sector_id__in=sector_ids)
    return Q(**{f"{prefix}id__in": members.values("dataset_id")})


def _platform_q(sector_ids: Optional[FrozenSet[UUID]], prefix: str) -> Q:
    # The one platform-scope rule: the corpus, in the given sectors (None: no narrowing).
    corpus = public_published_datasets_q(prefix)
    if sector_ids is None:
        return corpus
    return corpus & _in_sectors_q(sector_ids, prefix)


def platform_scope_q(prefix: str = "") -> Q:
    """Corpus datasets in platform scope, sectors resolved now. ``prefix`` reaches the dataset."""
    return _platform_q(platform_sector_ids(), prefix)


def dataset_in_scope_q(scope: "ResolvedScope", prefix: str = "") -> Q:
    """Corpus datasets inside an already-resolved scope. ``prefix`` reaches the dataset."""
    if scope.kind == "platform":
        return _platform_q(scope.sector_ids, prefix)
    return public_published_datasets_q(prefix) & Q(**{f"{prefix}id__in": scope.dataset_ids or ()})


def enabled_collaboratives_q() -> Q:
    """Published collaboratives that may be a scope (all of them when none are listed)."""
    enabled = Q(status=CollaborativeStatus.PUBLISHED.value)
    if settings.QE_ENABLED_COLLABORATIVES:
        enabled &= Q(public_id__in=settings.QE_ENABLED_COLLABORATIVES)
    return enabled


def processing_set_q() -> Q:
    """The datasets ``qe_sync`` works on: platform scope plus enabled collaboratives' corpus datasets."""
    sector_ids = platform_sector_ids()
    platform = _platform_q(sector_ids, "")
    if sector_ids is None:
        return platform
    members = Collaborative.datasets.through.objects.filter(
        collaborative__in=Collaborative.objects.filter(enabled_collaboratives_q())
    )
    return platform | (public_published_datasets_q() & Q(id__in=members.values("dataset_id")))


def load_corpus(chunk_size: int = CORPUS_CHUNK_SIZE) -> Iterator[List[Dataset]]:
    """The processing set in chunks of ``chunk_size`` datasets, ordered by id.

    Each dataset arrives with its organisation, tags, sectors, geographies,
    profile and every resource (with its data table, file details, profile and
    column rows in file order), so reading a chunk costs a fixed number of
    queries whatever its size. Pages by id (no OFFSET). The filter is built
    when this is called, not when the first chunk is read.
    """
    resources = (
        Resource.objects.select_related("resourcedatatable", "resourcefiledetails", "qe_profile")
        .prefetch_related(
            Prefetch("resourceschema_set", queryset=ResourceSchema.objects.order_by("id"))
        )
        .order_by("name", "id")
    )
    datasets = (
        Dataset.objects.filter(processing_set_q())
        .select_related("organization", "qe_profile")
        .prefetch_related("tags", "sectors", "geographies", Prefetch("resources", resources))
        .order_by("id")
    )

    def chunks() -> Iterator[List[Dataset]]:
        last_id: Optional[UUID] = None
        while True:
            page = datasets if last_id is None else datasets.filter(id__gt=last_id)
            chunk = list(page[:chunk_size])
            if not chunk:
                return
            yield chunk
            last_id = chunk[-1].id

    return chunks()


def get_resource_in_scope(resource_id: UUID, scope: "ResolvedScope") -> Resource:
    """One analysable resource inside the scope, with its dataset, data table and profile.

    One query. Raises NotFound when it doesn't exist, isn't analysable, or is
    outside the scope.
    """
    found = Resource.objects.select_related("dataset", "resourcedatatable", "qe_profile").filter(
        Q(pk=resource_id) & analysable_resource_q() & dataset_in_scope_q(scope, "dataset__")
    )
    return _one_or_not_found(
        list(found[:1]), reason="resource_not_in_scope", resource_id=str(resource_id)
    )


def get_dataset_in_scope(dataset_id: UUID, scope: "ResolvedScope") -> Dataset:
    """One corpus dataset inside the scope, with its organisation and profile. One query."""
    found = Dataset.objects.select_related("organization", "qe_profile").filter(
        Q(pk=dataset_id) & dataset_in_scope_q(scope)
    )
    return _one_or_not_found(
        list(found[:1]), reason="dataset_not_in_scope", dataset_id=str(dataset_id)
    )


def _one_or_not_found(rows: List[T], reason: str, **ids: Any) -> T:
    if not rows:
        raise NotFound(reason=reason, **ids)
    return rows[0]


def _sector_tree() -> Dict[UUID, Tuple[str, Optional[UUID]]]:
    return {
        sid: (str(slug or ""), parent)
        for sid, slug, parent in Sector.objects.values_list("id", "slug", "parent_id")
    }


def sector_slugs_with_parents() -> Dict[UUID, List[str]]:
    """Each sector's slug followed by its parents' slugs (one query), for search documents."""
    tree = _sector_tree()
    found: Dict[UUID, List[str]] = {}
    for sector_id in tree:
        slugs: List[str] = []
        current: Optional[UUID] = sector_id
        while current is not None and current in tree and tree[current][0] not in slugs:
            slugs.append(tree[current][0])
            current = tree[current][1]
        found[sector_id] = slugs
    return found


def platform_sector_slugs(sector_ids: Optional[FrozenSet[UUID]]) -> Optional[List[str]]:
    """The slugs of an already-resolved platform scope's sectors (None: no narrowing)."""
    if sector_ids is None:
        return None
    tree = _sector_tree()
    return sorted(tree[sid][0] for sid in sector_ids if sid in tree)


def keep_in_scope(
    dataset_ids: Iterable[str], resource_ids: Iterable[str], scope: "ResolvedScope"
) -> Tuple[Dict[str, Dataset], Dict[str, Resource]]:
    """The search hits still allowed now: corpus datasets in scope, and analysable tables in scope.

    The database check after Elasticsearch, so a stale index entry (unpublished,
    made private, moved out of the collaborative, deleted) is never served.
    Two queries on primary keys (at most 100 ids each).
    """
    resources = {
        str(r.id): r
        for r in Resource.objects.select_related("resourcedatatable", "qe_profile").filter(
            Q(pk__in=_uuids(resource_ids))
            & analysable_resource_q()
            & dataset_in_scope_q(scope, "dataset__")
        )
    }
    wanted = set(_uuids(dataset_ids)) | {r.dataset_id for r in resources.values()}
    datasets = {
        str(d.id): d
        for d in Dataset.objects.select_related("organization", "qe_profile").filter(
            Q(pk__in=wanted) & dataset_in_scope_q(scope)
        )
    }
    return datasets, {rid: r for rid, r in resources.items() if str(r.dataset_id) in datasets}


def _uuids(values: Iterable[str]) -> List[UUID]:
    found: List[UUID] = []
    for value in values:
        try:
            found.append(UUID(str(value)))
        except ValueError:
            continue
    return found
