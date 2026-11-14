"""What one query-engine call may see: ``platform`` or ``collaborative:<public id>``.

Every internal call (except the two summary endpoints) names its scope; the
backend has no default. A scope is resolved against the database on every
call and never stored or indexed, so attaching, detaching or unpublishing
takes effect immediately.

- ``parse_scope`` checks the text only (BadScope → 400).
- ``resolve_scope`` loads it: platform gets its sector narrowing resolved
  once; a collaborative must be PUBLISHED (and on ``QE_ENABLED_COLLABORATIVES``
  when that is set), else ScopeNotFound → 404. A collaborative's datasets are
  its attached corpus datasets, read now.
- ``scope_summary`` is what GET scope/ returns.

Query shapes: ``Collaborative.only("id", "title").get(public_id=?, status=PUBLISHED)``
on the unique public id; members through the collaborative-dataset through table.

Docs: api/views/query_engine/architecture.md
"""

from dataclasses import dataclass
from typing import Any, Dict, Final, FrozenSet, Literal, Optional
from uuid import UUID

from django.conf import settings

from api.models import Collaborative, Dataset
from api.services.query_engine.corpus import dataset_in_scope_q, platform_sector_ids
from api.services.query_engine.errors import BadScope, ScopeNotFound
from api.utils.dataset_access import public_published_datasets_q
from api.utils.enums import CollaborativeStatus
from api.utils.public_links import _PUBLIC_ID_RE

PLATFORM: Final = "platform"
COLLABORATIVE: Final = "collaborative"
COLLABORATIVE_PREFIX = f"{COLLABORATIVE}:"
MAX_SCOPE_DATASET_IDS = 2000

ScopeKind = Literal["platform", "collaborative"]


@dataclass(frozen=True)
class ScopeRef:
    """A parsed scope string, not yet checked against the database."""

    kind: ScopeKind
    public_id: Optional[str] = None


@dataclass(frozen=True)
class ResolvedScope:
    """A scope as the database says it is right now.

    Platform: ``sector_ids`` narrows it (None: the whole corpus), ``dataset_ids`` is None.
    Collaborative: ``dataset_ids`` are its attached corpus datasets.
    """

    kind: ScopeKind
    public_id: Optional[str] = None
    collaborative_id: Optional[int] = None
    title: Optional[str] = None
    dataset_ids: Optional[FrozenSet[UUID]] = None
    sector_ids: Optional[FrozenSet[UUID]] = None

    @property
    def text(self) -> str:
        return PLATFORM if self.kind == PLATFORM else f"{COLLABORATIVE_PREFIX}{self.public_id}"


def parse_scope(text: Any) -> ScopeRef:
    """Check a scope string's shape. Raises BadScope for anything but the two forms."""
    if text == PLATFORM:
        return ScopeRef(kind=PLATFORM)
    if isinstance(text, str) and text.startswith(COLLABORATIVE_PREFIX):
        public_id = text[len(COLLABORATIVE_PREFIX) :]
        if _PUBLIC_ID_RE.fullmatch(public_id):
            return ScopeRef(kind=COLLABORATIVE, public_id=public_id)
    raise BadScope()


def resolve_scope(text: Any) -> ResolvedScope:
    """Parse a scope string and load what it covers now. Raises BadScope or ScopeNotFound."""
    ref = parse_scope(text)
    if ref.kind == PLATFORM:
        return ResolvedScope(kind=PLATFORM, sector_ids=platform_sector_ids())

    enabled = settings.QE_ENABLED_COLLABORATIVES
    if enabled and ref.public_id not in enabled:
        raise ScopeNotFound(reason="collaborative_not_enabled", public_id=ref.public_id)
    collaborative = (
        Collaborative.objects.only("id", "title")
        .filter(public_id=ref.public_id, status=CollaborativeStatus.PUBLISHED.value)
        .first()
    )
    if collaborative is None:
        raise ScopeNotFound(reason="collaborative_not_published", public_id=ref.public_id)
    members = Dataset.objects.filter(
        public_published_datasets_q(), collaborative__id=collaborative.id
    ).values_list("id", flat=True)
    return ResolvedScope(
        kind=COLLABORATIVE,
        public_id=ref.public_id,
        collaborative_id=collaborative.id,
        title=collaborative.title,
        dataset_ids=frozenset(members),
    )


def scope_summary(scope: ResolvedScope, include_dataset_ids: bool = False) -> Dict[str, Any]:
    """What GET scope/ returns: kind, id, title, dataset count and (when asked) dataset ids.

    Ids are capped at MAX_SCOPE_DATASET_IDS, ordered by id; the count is exact.
    """
    datasets = Dataset.objects.filter(dataset_in_scope_q(scope))
    summary: Dict[str, Any] = {
        "kind": scope.kind,
        "public_id": scope.public_id,
        "title": scope.title,
        "dataset_count": datasets.count(),
    }
    if include_dataset_ids:
        ids = datasets.order_by("id").values_list("id", flat=True)[:MAX_SCOPE_DATASET_IDS]
        summary["dataset_ids"] = [str(dataset_id) for dataset_id in ids]
    return summary
