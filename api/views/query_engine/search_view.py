"""POST search/ — find the datasets and tables that answer a question, inside a scope.

Hybrid search (keywords + meaning) over the query engine's own index, then a
database check that every hit is still in the corpus and the scope, then the
system-wide reranker, then one result per dataset with its best tables. The
answer says when even the best match is weak, and which parts ran degraded
(``vector`` when the question couldn't be embedded, ``rerank`` when the
reranker failed). Elasticsearch down → 503 ``search_unavailable``.

Docs: ./architecture.md
"""

import structlog
from rest_framework.request import Request
from rest_framework.response import Response

from api.services.query_engine.scope import resolve_scope
from api.services.query_engine.search import (
    build_search_filters,
    embed_question,
    empty_search_response,
    hybrid_search,
    judge_weak_match,
    keep_hits_in_scope,
    question_fingerprint,
    rerank_hits,
    scope_has_no_datasets,
    search_response,
)
from api.views.query_engine.base import InternalQeView
from api.views.query_engine.serializers import SearchRequestSerializer, read_input
from search.query_engine.ranking import group_by_dataset

logger = structlog.get_logger("dataspace.query_engine.search")


class SearchView(InternalQeView):
    def post(self, request: Request) -> Response:
        # Read and check the request.
        params = read_input(SearchRequestSerializer, request.data)
        query = params["query"]

        # Work out what the scope covers right now.
        scope = resolve_scope(params["scope"])

        # A collaborative with nothing in the corpus has nothing to find.
        if scope_has_no_datasets(scope):
            return Response(empty_search_response(scope))

        # Turn the question into a vector; keywords only if that fails.
        vector, degraded = embed_question(query)

        # Filters both legs share: scope, places, years.
        filters = build_search_filters(
            scope, params["geographies"], params.get("year_from"), params.get("year_to")
        )

        # Keyword and vector search in one request, fused by rank (503 if search is down).
        hits, vector_used = hybrid_search(query, vector, filters)
        if vector is not None and not vector_used:
            degraded.append("vector")

        # Drop anything no longer in the corpus or the scope, before ranking further.
        hits, datasets, resources = keep_hits_in_scope(hits, scope)

        # Let the reranker put the best matches first.
        hits, reranked = rerank_hits(query, hits)
        if hits and not reranked:
            degraded.append("rerank")

        # One result per dataset, with its best tables.
        groups = group_by_dataset(hits, params["size"])

        # Is even the best match too weak to offer?
        weak = judge_weak_match(hits, reranked, vector_used)

        logger.info(
            "qe_search_done",
            scope_kind=scope.kind,
            results=len(groups),
            weak_match=weak,
            degraded=degraded,
            **question_fingerprint(query),
        )
        return Response(search_response(scope, groups, datasets, resources, weak, degraded))
