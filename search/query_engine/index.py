"""The one gateway to the query engine's AI-search index in Elasticsearch.

Everything that reads or writes the catalog index goes through here, so tests
patch this module and never reach a cluster. Every Elasticsearch failure
becomes ``SearchIndexError`` (logged by error type only).

- ``ensure_search_index``: create ``<alias>_v1`` and the alias when missing;
  **refuse** (``IndexDimsMismatch``) when the live index's vector size differs
  from QE_EMBEDDINGS_DIMS — writing then would corrupt kNN; run
  ``qe_sync --rebuild-index``.
- ``read_doc_states``: every doc id with its ``card_hash`` and whether it has a vector (scan).
- ``upsert_docs`` / ``delete_docs``: bulk writes.
- ``multi_search``: several search bodies in one ``msearch``.
- ``create_next_index`` / ``swap_alias`` / ``delete_index``: the rebuild steps;
  the alias moves atomically, so the old index serves search until then.

Docs: api/views/query_engine/architecture.md
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import structlog
from django.conf import settings
from elasticsearch import helpers
from elasticsearch_dsl.connections import connections

from search.documents.qe_catalog_document import VECTOR_FIELD, catalog_index

logger = structlog.get_logger("dataspace.query_engine.search_index")

SCAN_SIZE = 1000
_VERSION = re.compile(r"_v(\d+)$")


class SearchIndexError(Exception):
    """Elasticsearch could not do what was asked."""


class IndexDimsMismatch(SearchIndexError):
    """The live index stores vectors of another size than the settings ask for."""


@dataclass(frozen=True)
class DocState:
    card_hash: str
    has_embedding: bool


def alias_name() -> str:
    return str(settings.QE_SEARCH_INDEX)


def _es() -> Any:
    return connections.get_connection()


def _fail(action: str, error: BaseException) -> SearchIndexError:
    logger.warning("qe_search_index_failed", action=action, error_type=type(error).__name__)
    return SearchIndexError(action)


def live_index_name() -> Optional[str]:
    """The physical index the alias points at, or None when there is no alias yet."""
    try:
        es = _es()
        if not es.indices.exists_alias(name=alias_name()):
            return None
        return str(max(es.indices.get_alias(name=alias_name()), key=_version_number))
    except Exception as error:
        raise _fail("read_alias", error) from error


def _version_number(name: str) -> int:
    found = _VERSION.search(name)
    return int(found.group(1)) if found else 0


def _live_dims(index: str) -> Optional[int]:
    mapping = _es().indices.get_mapping(index=index)
    properties = mapping[index]["mappings"].get("properties", {})
    dims = properties.get(VECTOR_FIELD, {}).get("dims")
    return int(dims) if dims is not None else None


def ensure_search_index(dims: int) -> str:
    """The live index name, creating version 1 and the alias when missing."""
    current = live_index_name()
    try:
        if current is None:
            name = f"{alias_name()}_v1"
            catalog_index(name, dims).create(using=_es())
            _es().indices.put_alias(index=name, name=alias_name())
            logger.info("qe_search_index_created", index=name, dims=dims)
            return name
        live = _live_dims(current)
    except Exception as error:
        raise _fail("ensure_index", error) from error
    if live != dims:
        logger.error("qe_search_index_dims_mismatch", index=current, live_dims=live, dims=dims)
        raise IndexDimsMismatch(current)
    return current


def read_doc_states(index: str) -> Dict[str, DocState]:
    """Every document's card hash and whether it has a vector."""
    try:
        hits = helpers.scan(
            _es(),
            index=index,
            query={"query": {"match_all": {}}, "_source": ["card_hash", "has_embedding"]},
            size=SCAN_SIZE,
        )
        return {
            hit["_id"]: DocState(
                card_hash=str(hit["_source"].get("card_hash") or ""),
                has_embedding=bool(hit["_source"].get("has_embedding")),
            )
            for hit in hits
        }
    except Exception as error:
        raise _fail("read_states", error) from error


def upsert_docs(index: str, docs: Iterable[Tuple[str, Dict[str, Any]]]) -> int:
    """Write (replace) documents by id; returns how many were written."""
    actions = [
        {"_op_type": "index", "_index": index, "_id": doc_id, "_source": body}
        for doc_id, body in docs
    ]
    if not actions:
        return 0
    try:
        written, _ = helpers.bulk(_es(), actions, raise_on_error=True)
    except Exception as error:
        raise _fail("upsert", error) from error
    return int(written)


def delete_docs(index: str, doc_ids: Iterable[str]) -> int:
    """Delete documents by id (ones already gone are fine); returns how many were asked."""
    actions = [{"_op_type": "delete", "_index": index, "_id": doc_id} for doc_id in doc_ids]
    if not actions:
        return 0
    try:
        helpers.bulk(_es(), actions, raise_on_error=False, raise_on_exception=True)
    except Exception as error:
        raise _fail("delete", error) from error
    return len(actions)


def multi_search(bodies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run several search bodies against the alias in one request; one response each.

    A body that failed on its own comes back as ``{"error": ...}`` (logged), so
    the caller can still use the others; a failed request raises.
    """
    searches: List[Dict[str, Any]] = []
    for body in bodies:
        searches.extend([{"index": alias_name()}, body])
    try:
        response = _es().msearch(searches=searches)
    except Exception as error:
        raise _fail("msearch", error) from error
    responses = list(response["responses"])
    for position, item in enumerate(responses):
        if "error" in item:
            logger.warning(
                "qe_search_leg_failed", leg=position, error_type=str(item["error"].get("type"))
            )
    return responses


def create_next_index(dims: int) -> Tuple[str, Optional[str]]:
    """Create the next physical index version; returns (new name, current live name)."""
    current = live_index_name()
    version = _version_number(current) + 1 if current else 1
    name = f"{alias_name()}_v{version}"
    try:
        # A rebuild that was killed half-way leaves this version behind, never aliased.
        _es().indices.delete(index=name, ignore_unavailable=True)
        catalog_index(name, dims).create(using=_es())
    except Exception as error:
        raise _fail("create_index", error) from error
    return name, current


def swap_alias(new: str, old: Optional[str]) -> None:
    """Point the alias at ``new`` in one atomic step."""
    actions: List[Dict[str, Any]] = [{"add": {"index": new, "alias": alias_name()}}]
    if old:
        actions.insert(0, {"remove": {"index": old, "alias": alias_name()}})
    try:
        _es().indices.update_aliases(actions=actions)
    except Exception as error:
        raise _fail("swap_alias", error) from error


def delete_index(name: str) -> None:
    """Delete a physical index (a missing one is fine)."""
    try:
        _es().indices.delete(index=name, ignore_unavailable=True)
    except Exception as error:
        raise _fail("delete_index", error) from error
