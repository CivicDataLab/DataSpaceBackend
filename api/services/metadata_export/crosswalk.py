"""Standards crosswalk engine.

Nothing here knows the name of a standard: every property, node type, context
and obligation comes from ``contracts/crosswalk.json`` (owned by this repo; see
``contracts/README.md``). Add a standard to that file and this module exports
it unchanged. The record it reads is a plain dict keyed by the contract's
``dataspace_field`` names, produced by ``adapter.py``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONTRACT_PATH = Path(__file__).resolve().parent / "contracts" / "crosswalk.json"

# Value types that must be a URI on the way out; a bare name is reported.
MUST_RESOLVE = {"uri", "concept", "location"}
# Value types written as {"@id": …} when the standard's uri_style is "node".
REFERENCE_TYPES = {"uri", "concept", "location", "agent"}
# FOAF agent classes -> schema.org classes, for standards whose uri_style is not "node".
SCHEMA_AGENT_TYPES = {
    "foaf:Organization": "Organization",
    "foaf:Person": "Person",
    "foaf:Agent": "Organization",
}

EMPTY = (None, "", [], {})


def _is_uri(value: Any) -> bool:
    return isinstance(value, str) and (value.startswith("http://") or value.startswith("https://"))


class Crosswalk:
    def __init__(self, data: dict):
        self.data = data
        concepts = data.get("concepts", [])
        # The contract ships concepts as a list (each with a "key") or a dict keyed by concept.
        if isinstance(concepts, dict):
            self.concepts: Dict[str, dict] = {k: dict(v, key=k) for k, v in concepts.items()}
        else:
            self.concepts = {c["key"]: c for c in concepts}
        self.standards: Dict[str, dict] = data["standards"]

    @classmethod
    @lru_cache(maxsize=1)
    def load(cls, path: Optional[str] = None) -> "Crosswalk":
        with open(path or CONTRACT_PATH, encoding="utf-8") as fh:
            return cls(json.load(fh))

    # ------------------------------------------------------------------ info
    def standard_ids(self) -> List[str]:
        return list(self.standards.keys())

    def standard(self, sid: str) -> dict:
        try:
            return self.standards[sid]
        except KeyError as exc:
            raise KeyError(f"Unknown standard '{sid}'. Known: {', '.join(self.standards)}") from exc

    def gaps(self, sid: str) -> List[dict]:
        """Concepts this standard cannot carry."""
        return list(self.standard(sid).get("gaps", []))

    # ---------------------------------------------------------------- export
    def export(self, record: dict, sid: str) -> dict:
        doc, _ = self.export_with_report(record, sid)
        return doc

    def export_with_report(self, record: dict, sid: str) -> Tuple[dict, dict]:
        return self._export(record, self.standard(sid))

    def _export(self, record: dict, std: dict) -> Tuple[dict, dict]:
        node_types = std["node_types"]
        uri_style = std.get("uri_style", "node")

        doc: Dict[str, Any] = {"@context": std["context"]}
        if "dataset" in node_types:
            doc["@type"] = node_types["dataset"]

        report: Dict[str, list] = {
            "dropped": [],  # platform has a value, standard has no binding
            "unresolved": [],  # needs a URI, got a name string
            "missing_mandatory": [],  # standard wants it, platform had nothing
        }

        # Entries nested under another property (a period, a vCard) are
        # collected per parent and attached once at the end.
        nested: Dict[Tuple[str, str], Dict[str, Any]] = {}
        by_node: Dict[str, List[dict]] = {}
        for entry in std["export"]:
            by_node.setdefault(entry["node"], []).append(entry)

        # --- dataset-level, plus anything nested under it -------------------
        for entry in by_node.get("dataset", []) + by_node.get("period", []):
            value = self._platform_value(record, entry)
            if value in EMPTY:
                if entry["obligation"] == "mandatory":
                    report["missing_mandatory"].append(entry["concept"])
                continue
            rendered = self._render(value, entry, uri_style, report)
            if entry.get("parent_property"):
                nested.setdefault(("dataset", entry["parent_property"]), {})[
                    entry["property"]
                ] = rendered
            else:
                doc[entry["property"]] = rendered

        for (owner, parent_property), payload in nested.items():
            if owner == "dataset":
                doc[parent_property] = payload

        # --- distributions (one per resource) -------------------------------
        dist_entries = by_node.get("distribution", [])
        link = next((e for e in std["export"] if e["concept"] == "distribution"), None)
        if dist_entries and link:
            distributions = []
            for resource in record.get("resources") or []:
                dist: Dict[str, Any] = {}
                if "distribution" in node_types:
                    dist["@type"] = node_types["distribution"]
                for entry in dist_entries:
                    if entry["concept"] == "distribution":
                        continue
                    value = self._platform_value(resource, entry)
                    # DCAT requires accessURL on every Distribution; fall back to
                    # the download URL rather than emit an invalid Distribution.
                    if value in EMPTY and entry["concept"] == "access_url":
                        value = resource.get("download_url")
                    if value in EMPTY:
                        if entry["obligation"] == "mandatory":
                            report["missing_mandatory"].append(f"{entry['concept']} (distribution)")
                        continue
                    dist[entry["property"]] = self._render(value, entry, uri_style, report)
                if len(dist) > (1 if "@type" in dist else 0):
                    distributions.append(dist)
            if distributions:
                doc[link["property"]] = distributions

        # --- what this standard cannot carry --------------------------------
        for gap in std.get("gaps", []):
            concept = self.concepts.get(gap["concept"], {})
            field = concept.get("dataspace_field")
            if field and record.get(field) not in EMPTY:
                report["dropped"].append(
                    {
                        "concept": gap["concept"],
                        "dataspace_field": field,
                        "reason": gap.get("notes") or gap.get("reason"),
                    }
                )

        return doc, report

    def _platform_value(self, record: dict, entry: dict) -> Any:
        """Value for an export entry, by the field the contract binds it to."""
        field = entry.get("dataspace_field")
        return record.get(field) if field else None

    def _render(self, value: Any, entry: dict, uri_style: str, report: dict) -> Any:
        vtype = entry["value_type"]
        if isinstance(value, list):
            return [self._render_one(v, entry, vtype, uri_style, report) for v in value]
        rendered = self._render_one(value, entry, vtype, uri_style, report)
        return [rendered] if entry.get("repeatable") else rendered

    def _render_one(self, value: Any, entry: dict, vtype: str, uri_style: str, report: dict) -> Any:
        # Vocabulary values arrive as {"name": …, "uri": …} from the adapter.
        if isinstance(value, dict) and vtype in ("concept", "location", "uri", "agent"):
            if vtype == "agent" and uri_style == "node":
                agent = {"@type": value.get("@type", "foaf:Agent"), "foaf:name": value.get("name")}
                if value.get("uri"):
                    agent["@id"] = value["uri"]
                return agent
            if vtype == "agent":
                kind = SCHEMA_AGENT_TYPES.get(value.get("@type", ""), "Organization")
                return {"@type": kind, "name": value.get("name")} | (
                    {"url": value["uri"]} if value.get("uri") else {}
                )
            value = value.get("uri") or value.get("name") or value.get("label")
        elif isinstance(value, dict) and vtype in ("literal", "langstring"):
            # A vocabulary value written where the standard wants its plain name.
            value = value.get("label") or value.get("name") or value.get("uri")

        if vtype in MUST_RESOLVE and not _is_uri(value):
            report["unresolved"].append(
                {
                    "concept": entry["concept"],
                    "value": value,
                    "vocabulary": entry.get("controlled_vocabulary"),
                    "expected": f"{vtype} — a resolvable URI",
                }
            )
            return value  # emit what we have; the report says it is not a URI

        if vtype in REFERENCE_TYPES and uri_style == "node" and _is_uri(value):
            return {"@id": value}
        if vtype == "bytes":
            try:
                return int(value)
            except (TypeError, ValueError):
                return value
        return value
