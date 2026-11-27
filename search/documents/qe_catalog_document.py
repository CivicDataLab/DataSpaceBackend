"""The AI-search index for the query engine: one document per dataset and one per table.

A plain elasticsearch_dsl mapping, deliberately **not** a django-elasticsearch-dsl
Document and not imported by ``search/documents/__init__.py``: registered
documents are written on every model save and refilled by
``sync_search_mappings`` at every container start, which would call the
embeddings service inside publish requests and at boot. ``qe_sync`` alone
writes this index (search/query_engine/index.py).

Physical indexes are ``<QE_SEARCH_INDEX>_v<n>`` behind the alias
QE_SEARCH_INDEX; doc ids are ``d:<dataset id>`` and ``r:<resource id>``. The
vector size comes from QE_EMBEDDINGS_DIMS; a new size needs
``qe_sync --rebuild-index``.

Docs: api/views/query_engine/architecture.md
"""

from elasticsearch_dsl import Boolean, Date, DenseVector, Index, Integer, Keyword, Mapping, Text

from search.documents.analysers import html_strip, ngram_analyser, title_subfields

VECTOR_FIELD = "embedding"


def catalog_mapping(dims: int) -> Mapping:
    """The fields of a catalog document, with a ``dims``-sized cosine vector."""
    mapping = Mapping()
    for name in ("doc_kind", "dataset_id", "resource_id", "organization_id", "geo_level"):
        mapping.field(name, Keyword())
    mapping.field("title", Text(analyzer=ngram_analyser, fields=title_subfields()))
    mapping.field("search_text", Text(analyzer=html_strip))
    mapping.field("summary", Text(analyzer=html_strip))
    # What the reranker reads: the card text, cut short; stored, not searched.
    mapping.field("rerank_text", Text(index=False))
    mapping.field("sectors", Keyword(multi=True))
    mapping.field("geographies", Keyword(multi=True))
    mapping.field("year_min", Integer())
    mapping.field("year_max", Integer())
    mapping.field("analysable", Boolean())
    mapping.field("has_embedding", Boolean())
    mapping.field(VECTOR_FIELD, DenseVector(dims=dims, index=True, similarity="cosine"))
    mapping.field("embedding_model", Keyword())
    mapping.field("card_hash", Keyword())
    mapping.field("indexed_at", Date())
    return mapping


def catalog_index(name: str, dims: int) -> Index:
    """A physical catalog index (1 shard, 0 replicas, like the public dataset index)."""
    index = Index(name)
    index.settings(number_of_shards=1, number_of_replicas=0)
    index.mapping(catalog_mapping(dims))
    return index
