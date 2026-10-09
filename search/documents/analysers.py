from elasticsearch_dsl import analyzer, tokenizer

html_strip = analyzer(
    "html_strip",
    tokenizer="standard",
    filter=["lowercase", "stop", "snowball"],
    char_filter=["html_strip"],
)
ngram_analyser = analyzer(
    "custom_analyser",
    tokenizer=tokenizer("trigram", "ngram", min_gram=4, max_gram=4),
    filter=["lowercase", "stop", "snowball"],
    char_filter=["html_strip"],
)


def title_subfields() -> dict:
    """Sub-fields every title-like field carries.

    - ``raw``: the whole title, for A-Z sorting and exact filters.
    - ``words``: whole words, lower-cased and stemmed (English), so short
      words like "GDP" and "AI" match and "floods" finds "flood". The main
      field's 4-letter chunks cannot do either.
    - ``prefix``: word beginnings (search-as-you-type), so "mang" finds
      "Mangrove" while typing.

    Built-in analysers only, so ``sync_search_mappings`` can add them to a live
    index and fill them in place, without a rebuild.
    """
    from django_elasticsearch_dsl import fields

    return {
        "raw": fields.KeywordField(multi=False),
        "words": fields.TextField(analyzer="english"),
        "prefix": fields.SearchAsYouTypeField(),
    }
