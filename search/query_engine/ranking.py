"""Merging and judging AI-search hits (pure).

- ``rrf_fuse``: reciprocal-rank fusion of the keyword and vector legs
  (score = Σ 1 / (60 + rank)); a hit found by only one leg is kept; ties keep
  the order they were first seen (keyword leg first).
- ``group_by_dataset``: one result per dataset, at the rank of its best hit,
  carrying its best (at most 3) tables.
- ``is_weak_match``: whether even the best result is a poor match, so the
  engine says "nothing good found" instead of guessing — by the reranker's top
  score when it ran; else (reranker down) by the top vector similarity with no
  keyword hit; else (keywords only) when nothing matched by keyword.

Docs: api/views/query_engine/architecture.md
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

RRF_K = 60
MAX_TABLES_PER_DATASET = 3


@dataclass
class Hit:
    """One search document with how each leg ranked it."""

    doc_id: str
    source: Dict[str, Any]
    keyword_rank: Optional[int] = None
    vector_rank: Optional[int] = None
    vector_score: Optional[float] = None
    fused: float = 0.0
    rerank_score: Optional[float] = None

    @property
    def dataset_id(self) -> str:
        return str(self.source.get("dataset_id"))

    @property
    def resource_id(self) -> Optional[str]:
        value = self.source.get("resource_id")
        return str(value) if value else None


@dataclass
class Group:
    """A dataset's result: its own hit (if any) and its best tables."""

    dataset_id: str
    rank: int
    hits: List[Hit] = field(default_factory=list)

    @property
    def tables(self) -> List[Hit]:
        return [hit for hit in self.hits if hit.resource_id][:MAX_TABLES_PER_DATASET]

    @property
    def best(self) -> Hit:
        return self.hits[0]


def _leg(response: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any], float]]:
    return [
        (hit["_id"], hit.get("_source") or {}, float(hit.get("_score") or 0.0))
        for hit in response.get("hits", {}).get("hits", [])
    ]


def rrf_fuse(keyword: Dict[str, Any], vector: Optional[Dict[str, Any]]) -> List[Hit]:
    """Fuse the two legs' responses (vector may be None) into one ranked list."""
    hits: Dict[str, Hit] = {}
    for rank, (doc_id, source, _) in enumerate(_leg(keyword), start=1):
        hit = hits.setdefault(doc_id, Hit(doc_id=doc_id, source=source))
        hit.keyword_rank = rank
        hit.fused += 1.0 / (RRF_K + rank)
    for rank, (doc_id, source, score) in enumerate(_leg(vector or {}), start=1):
        hit = hits.setdefault(doc_id, Hit(doc_id=doc_id, source=source))
        hit.vector_rank = rank
        hit.vector_score = score
        hit.fused += 1.0 / (RRF_K + rank)
    order = {doc_id: position for position, doc_id in enumerate(hits)}
    return sorted(hits.values(), key=lambda hit: (-hit.fused, order[hit.doc_id]))


def group_by_dataset(hits: Sequence[Hit], size: int) -> List[Group]:
    """At most ``size`` datasets, in the order of their best hit."""
    groups: Dict[str, Group] = {}
    for rank, hit in enumerate(hits):
        group = groups.setdefault(hit.dataset_id, Group(dataset_id=hit.dataset_id, rank=rank))
        group.hits.append(hit)
    return sorted(groups.values(), key=lambda group: group.rank)[:size]


def is_weak_match(
    hits: Sequence[Hit],
    *,
    reranked: bool,
    vector_used: bool,
    rerank_threshold: float,
    similarity_threshold: float,
) -> bool:
    """Whether the best result is too poor to offer (see the module comment)."""
    if not hits:
        return True
    if reranked:
        top = max((hit.rerank_score or 0.0) for hit in hits)
        return top < rerank_threshold
    has_keyword_hit = any(hit.keyword_rank is not None for hit in hits)
    if vector_used:
        top_similarity = max((hit.vector_score or 0.0) for hit in hits)
        return top_similarity < similarity_threshold and not has_keyword_hit
    return not has_keyword_hit
