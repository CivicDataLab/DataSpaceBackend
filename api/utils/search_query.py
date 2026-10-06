"""The text part of the listing-page search queries.

The per-type search views used a term-level ``fuzzy`` query, which does not
analyse the search text: it is compared, unsplit and case-sensitive, against
the stored tokens. Titles are stored as 4-letter n-grams, so most words,
capital letters and phrases never matched (#202, #225, #226).

``text_query`` builds an analysed query instead. The search text goes through
each field's own analyser, exactly like the stored text, so both sides compare
like with like:

- one ``multi_match`` where every token must be found (precise), and
- one ``multi_match`` with typo tolerance where most tokens must be found.

Fields inside nested objects (``resources.name``, ``user.name``,
``metadata.value`` …) are wrapped in the ``nested`` query Elasticsearch needs
for them; without it they silently match nothing.

Known limit, tracked in #226: with 4-gram titles, a word shorter than four
letters (GDP, AI) produces no token and cannot match a title.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from elasticsearch_dsl import Q as ESQ
from elasticsearch_dsl.query import Query as ESQuery

# With typos allowed: searches of up to 3 tokens need all of them, longer
# ones need 80%. A plain "80%" lets a 2-token search match on 1 token, which
# pulled in unrelated titles ("Grade" matched "Ridership").
TYPO_TOLERANT_MIN_MATCH = "3<80%"

# Primary title fields count three times as much as the rest.
DEFAULT_BOOSTS: Dict[str, int] = {"title": 3, "name": 3, "display_name": 3}


def nested_paths(document_class: object) -> set[str]:
    """Top-level fields mapped as ``nested`` on a search document."""
    mapping = document_class._doc_type.mapping.to_dict()  # type: ignore[attr-defined]
    properties = mapping.get("properties", {})
    return {name for name, spec in properties.items() if spec.get("type") == "nested"}


def _match_clause(query: str, fields: List[str]) -> ESQuery:
    return ESQ(
        "bool",
        should=[
            ESQ("multi_match", query=query, fields=fields, operator="and"),
            ESQ(
                "multi_match",
                query=query,
                fields=fields,
                fuzziness="AUTO",
                prefix_length=1,  # typo may not be in a token's first letter; cuts noise on 4-grams
                minimum_should_match=TYPO_TOLERANT_MIN_MATCH,
            ),
        ],
        minimum_should_match=1,
    )


def text_query(
    query: str,
    fields: Iterable[str],
    nested: Iterable[str] = (),
    boosts: Optional[Dict[str, int]] = None,
) -> ESQuery:
    """Analysed search over ``fields``; match-all for an empty search.

    ``nested`` lists the top-level object names mapped as nested on the
    document (see ``nested_paths``). ``boosts`` weights fields, e.g.
    ``{"title": 3}``; defaults to ``DEFAULT_BOOSTS``.
    """
    text = (query or "").strip()
    if not text:
        return ESQ("match_all")

    nested_set = set(nested)
    boosts = DEFAULT_BOOSTS if boosts is None else boosts
    groups: Dict[Optional[str], List[str]] = {}
    for field in fields:
        root = field.split(".", 1)[0]
        path = root if root in nested_set and "." in field else None
        weight = boosts.get(field)
        groups.setdefault(path, []).append(f"{field}^{weight}" if weight else field)

    clauses: List[ESQuery] = []
    for path, group in groups.items():
        clause = _match_clause(text, group)
        if path:
            clause = ESQ("nested", path=path, query=clause, ignore_unmapped=True)
        clauses.append(clause)

    return clauses[0] if len(clauses) == 1 else ESQ("bool", should=clauses, minimum_should_match=1)
