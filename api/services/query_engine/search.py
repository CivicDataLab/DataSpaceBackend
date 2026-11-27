"""The steps of an AI search (the flow is api/views/query_engine/search_view.py).

1. ``embed_question``: the question's vector, or None and ``degraded: ["vector"]``
   when the embeddings service fails (search continues by keywords only).
2. ``build_search_filters``: the scope (a collaborative's dataset ids, or the
   platform's sector slugs with sub-sectors), places expanded with the places
   inside them, and an overlapping year range.
3. ``hybrid_search``: both legs in one ``msearch``, fused by reciprocal rank.
   A failed vector leg falls back to keywords (``degraded: ["vector"]``);
   Elasticsearch down or the keyword leg failing → ``SearchUnavailable`` (503).
4. ``keep_hits_in_scope``: the database check — hits that left the corpus or
   the scope since they were indexed are dropped, before anything is ranked.
5. ``rerank_hits``: the top 30 reordered by the system-wide reranker; on
   failure the fused order stays and ``degraded`` gains "rerank".
6. ``search_response``: one result per dataset (≤ ``size``) with its best ≤ 3
   tables, titles and summaries read from the database (summaries only when
   current, labelled generated), and the weak-match flag.

Logs carry the question's length and a short hash, never its text.

Docs: api/views/query_engine/architecture.md
"""

import hashlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

import structlog
from django.conf import settings

from api.models import Dataset, Geography, Resource
from api.services.query_engine.corpus import keep_in_scope, platform_sector_slugs
from api.services.query_engine.embeddings import (
    EmbeddingsUnavailable,
    embed_query,
    embeddings_configured,
)
from api.services.query_engine.errors import SearchUnavailable
from api.services.query_engine.profile_overlay import coverage
from api.services.query_engine.profile_views import current_summary
from api.services.query_engine.profiles import ready_stats
from api.services.query_engine.reranker import (
    RerankUnavailable,
    rerank,
    rerank_configured,
    weak_match_threshold,
)
from api.services.query_engine.scope import ResolvedScope
from search.query_engine.index import SearchIndexError, multi_search
from search.query_engine.queries import keyword_body, search_filters, vector_body
from search.query_engine.ranking import Group, Hit, group_by_dataset, is_weak_match, rrf_fuse

logger = structlog.get_logger("dataspace.query_engine.search")

RERANK_TOP = 30


def question_fingerprint(query: str) -> Dict[str, Any]:
    """Log fields for a question: its length and a short hash, never the text."""
    return {
        "query_length": len(query),
        "query_hash": hashlib.sha256(query.encode("utf-8")).hexdigest()[:12],
    }


def scope_has_no_datasets(scope: ResolvedScope) -> bool:
    """A collaborative with no corpus datasets: nothing to search, no Elasticsearch call."""
    return scope.kind == "collaborative" and not scope.dataset_ids


def embed_question(query: str) -> Tuple[Optional[List[float]], List[str]]:
    """The question's vector and the degraded modes so far (``["vector"]`` when it failed).

    No call at all when no embeddings service is configured.
    """
    if not embeddings_configured():
        return None, ["vector"]
    try:
        return embed_query(query), []
    except EmbeddingsUnavailable:
        return None, ["vector"]


def build_search_filters(
    scope: ResolvedScope,
    geographies: Sequence[str] = (),
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """The filters both search legs share, for this scope and request."""
    places = (
        Geography.get_geography_names_with_descendants(list(geographies)) if geographies else []
    )
    return search_filters(
        dataset_ids=(
            [str(i) for i in scope.dataset_ids or ()] if scope.kind == "collaborative" else None
        ),
        sector_slugs=platform_sector_slugs(scope.sector_ids) if scope.kind == "platform" else None,
        geographies=places,
        year_from=year_from,
        year_to=year_to,
    )


def hybrid_search(
    query: str, vector: Optional[List[float]], filters: List[Dict[str, Any]]
) -> Tuple[List[Hit], bool]:
    """Keyword and vector legs in one request, fused; and whether the vector leg ran.

    A failed vector leg (e.g. the index still has vectors of another size
    while it is rebuilt) falls back to the keyword leg. The keyword leg or
    the request failing raises SearchUnavailable.
    """
    bodies = [keyword_body(query, filters)]
    if vector is not None:
        bodies.append(vector_body(vector, filters))
    try:
        responses = multi_search(bodies)
    except SearchIndexError as error:
        raise SearchUnavailable(reason="search_index_failed") from error
    if "error" in responses[0]:
        raise SearchUnavailable(reason="keyword_leg_failed")
    vector_response = responses[1] if vector is not None and "error" not in responses[1] else None
    return rrf_fuse(responses[0], vector_response), vector_response is not None


def keep_hits_in_scope(
    hits: List[Hit], scope: ResolvedScope
) -> Tuple[List[Hit], Dict[str, Dataset], Dict[str, Resource]]:
    """Only hits whose dataset (and table) are still in the corpus and the scope."""
    datasets, resources = keep_in_scope(
        {hit.dataset_id for hit in hits},
        {hit.resource_id for hit in hits if hit.resource_id},
        scope,
    )
    kept = [
        hit
        for hit in hits
        if (hit.resource_id in resources if hit.resource_id else hit.dataset_id in datasets)
    ]
    return kept, datasets, resources


def rerank_hits(query: str, hits: List[Hit]) -> Tuple[List[Hit], bool]:
    """The top 30 hits in the reranker's order, and whether the reranker ran."""
    top = hits[:RERANK_TOP]
    if not top or not rerank_configured():
        return top, False
    try:
        order = rerank(
            query,
            [str(hit.source.get("rerank_text") or hit.source.get("title") or "") for hit in top],
        )
    except RerankUnavailable:
        return top, False
    ranked: List[Hit] = []
    for index, score in order:
        top[index].rerank_score = score
        ranked.append(top[index])
    return ranked, True


def _table_entry(hit: Hit, resource: Resource) -> Dict[str, Any]:
    stats = ready_stats(resource) or {}
    found = coverage(stats)
    return {
        "resource_id": str(resource.id),
        "name": resource.name,
        "analysable": bool(stats.get("analysable")),
        "years": {"from": found["year_min"], "to": found["year_max"]},
        "geo_level": found["geo_level"],
        "score": round(hit.rerank_score if hit.rerank_score is not None else hit.fused, 6),
    }


def search_response(
    scope: ResolvedScope,
    groups: List[Group],
    datasets: Dict[str, Dataset],
    resources: Dict[str, Resource],
    weak_match: bool,
    degraded: List[str],
) -> Dict[str, Any]:
    """The response body: one entry per dataset, best first."""
    results = []
    for group in groups:
        dataset = datasets[group.dataset_id]
        best = group.best
        results.append(
            {
                "dataset_id": str(dataset.id),
                "title": dataset.title,
                "organization": dataset.organization.name if dataset.organization else None,
                "summary": current_summary(getattr(dataset, "qe_profile", None)),
                "score": round(
                    best.rerank_score if best.rerank_score is not None else best.fused, 6
                ),
                "tables": [
                    _table_entry(hit, resources[hit.resource_id])
                    for hit in group.tables
                    if hit.resource_id in resources
                ],
            }
        )
    return {"scope": scope.text, "weak_match": weak_match, "degraded": degraded, "results": results}


def judge_weak_match(hits: List[Hit], reranked: bool, vector_used: bool) -> bool:
    """Whether the best result is too poor to offer, with the active thresholds."""
    return is_weak_match(
        hits,
        reranked=reranked,
        vector_used=vector_used,
        # Only needed (and only knowable) when the reranker ran.
        rerank_threshold=weak_match_threshold() if reranked else 0.0,
        similarity_threshold=float(settings.QE_WEAK_MATCH_SIMILARITY),
    )


def empty_search_response(scope: ResolvedScope) -> Dict[str, Any]:
    """The answer when the scope has nothing to search."""
    return {"scope": scope.text, "weak_match": True, "degraded": [], "results": []}
