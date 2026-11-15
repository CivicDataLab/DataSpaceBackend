"""The two search legs of an AI search, sharing one set of filters.

- **keyword (BM25)**: the shared analysed text query (``text_query``) over
  ``title`` (×3, with its whole-word and prefix sub-fields) and ``search_text``;
- **vector (kNN)**: ``k=50`` nearest documents by cosine over the embedding,
  ``num_candidates=200``.

Both legs ask for 50 results so fusion sees every vector hit, and both carry
the same filters: the collaborative's dataset ids (collaborative scope), the
configured sector slugs with their sub-sectors (platform scope narrowed by
QE_PLATFORM_SECTORS), places (already expanded with the places inside them),
and a year range that overlaps the request (documents with no years pass).
The vector is never returned.

Pure: builds request bodies only.

Docs: api/views/query_engine/architecture.md
"""

from typing import Any, Dict, List, Optional, Sequence

from api.utils.search_query import text_query
from search.documents.qe_catalog_document import VECTOR_FIELD

LEG_SIZE = 50
KNN_K = 50
KNN_CANDIDATES = 200
SOURCE_FIELDS = ["doc_kind", "dataset_id", "resource_id", "title", "rerank_text"]


def search_filters(
    dataset_ids: Optional[Sequence[str]] = None,
    sector_slugs: Optional[Sequence[str]] = None,
    geographies: Sequence[str] = (),
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """The filter clauses both legs share (an empty list filters nothing)."""
    filters: List[Dict[str, Any]] = []
    if dataset_ids is not None:
        filters.append({"terms": {"dataset_id": sorted(dataset_ids)}})
    if sector_slugs is not None:
        filters.append({"terms": {"sectors": sorted(sector_slugs)}})
    if geographies:
        filters.append({"terms": {"geographies": sorted(geographies)}})
    if year_from is not None or year_to is not None:
        overlap: List[Dict[str, Any]] = []
        if year_to is not None:
            overlap.append({"range": {"year_min": {"lte": year_to}}})
        if year_from is not None:
            overlap.append({"range": {"year_max": {"gte": year_from}}})
        filters.append(
            {
                "bool": {
                    "should": [
                        {"bool": {"filter": overlap}},
                        {"bool": {"must_not": [{"exists": {"field": "year_min"}}]}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    return filters


def keyword_body(query: str, filters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The BM25 leg."""
    match = text_query(query, ["title", "search_text"], boosts={"title": 3}).to_dict()
    return {
        "size": LEG_SIZE,
        "_source": SOURCE_FIELDS,
        "query": {"bool": {"must": [match], "filter": filters}},
    }


def vector_body(vector: List[float], filters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The kNN leg."""
    return {
        "size": LEG_SIZE,
        "_source": SOURCE_FIELDS,
        "knn": {
            "field": VECTOR_FIELD,
            "query_vector": vector,
            "k": KNN_K,
            "num_candidates": KNN_CANDIDATES,
            "filter": filters,
        },
    }
