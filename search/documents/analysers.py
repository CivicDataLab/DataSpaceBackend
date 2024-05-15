from elasticsearch_dsl import analyzer, tokenizer

html_strip = analyzer(
    'html_strip',
    tokenizer="standard",
    filter=["lowercase", "stop", "snowball"],
    char_filter=["html_strip"]
)
ngram_analyser = analyzer('custom_analyser',
                          tokenizer=tokenizer('trigram', 'ngram', min_gram=4, max_gram=4),
                          filter=['lowercase', "stop", "snowball"],
                          char_filter=["html_strip"]
                          )
