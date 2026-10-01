"""Serialise a JSON-LD document into the RDF syntaxes catalogue harvesters ask for."""

from __future__ import annotations

import json
from typing import Dict, Tuple

# format id -> (rdflib serializer name, content type, file extension)
FORMATS: Dict[str, Tuple[str, str, str]] = {
    "jsonld": ("json-ld", "application/ld+json", "jsonld"),
    "turtle": ("turtle", "text/turtle", "ttl"),
    "rdfxml": ("xml", "application/rdf+xml", "rdf"),
    "ntriples": ("nt", "application/n-triples", "nt"),
}

# Croissant is defined as JSON-LD; its validator reads nothing else.
JSONLD_ONLY = {"croissant"}


def allowed_formats(standard_id: str) -> list:
    return ["jsonld"] if standard_id in JSONLD_ONLY else list(FORMATS)


def serialise(document: dict, fmt: str) -> Tuple[str, str, str]:
    """Return (body, content_type, extension) for the requested format."""
    serializer, content_type, ext = FORMATS[fmt]
    if fmt == "jsonld":
        return json.dumps(document, indent=2, ensure_ascii=False), content_type, ext
    from rdflib import Graph  # imported lazily: only non-JSON formats need it

    graph = Graph()
    graph.parse(data=json.dumps(document), format="json-ld")
    return graph.serialize(format=serializer), content_type, ext
