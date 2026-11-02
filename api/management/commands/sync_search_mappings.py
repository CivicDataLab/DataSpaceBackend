"""Bring existing Elasticsearch indexes up to date with the search documents.

Deploys never rebuild or re-map indexes. When a search document gains a field
(e.g. ``source_platform`` on datasets) or a sub-field (e.g. ``title.words``),
an index created before that change does not know it. A new top-level string
field would then get dynamically mapped as ``text`` and break aggregations on
it; a new sub-field would simply stay empty, so searches on it find nothing.

This command compares each registered document's mapping with its live index
and adds only what the index is missing:

- top-level fields, and
- sub-fields (``fields``) of existing top-level fields.

Elasticsearch allows adding both to a live mapping; it does not allow changing
or removing anything, and this command never tries. When sub-fields were added,
existing documents are filled in place with an update-by-query that runs in the
background on the Elasticsearch side (no rebuild, no downtime; until it
finishes, searches on the new sub-fields simply match fewer documents).

When top-level fields were added, their values come from the database, which
Elasticsearch cannot compute itself. Existing documents are then updated in
place with just those fields (a partial update per record, not a reindex), so
for example search results for old datasets get ``url_slug`` right away.

A registered document whose index does not exist yet (a new search type, such
as events) gets its index created, empty, with the full mapping and analysers.
Without that, the first published item would make Elasticsearch create the
index itself with guessed field types, and aggregations and sorting on it would
fail. The command never fails the process: problems are logged and reported, so
a search outage cannot stop the backend from starting.

    python manage.py sync_search_mappings            # apply
    python manage.py sync_search_mappings --dry-run  # report only

Runs from docker-entrypoint.sh after migrations.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List

import structlog
from django.core.management.base import BaseCommand
from django_elasticsearch_dsl.registries import registry
from elasticsearch.helpers import bulk

logger = structlog.get_logger("dataspace.search_mappings")


def missing_properties(existing: Dict[str, Any], desired: Dict[str, Any]) -> Dict[str, Any]:
    """Top-level fields present in ``desired`` but absent from ``existing``."""
    return {name: spec for name, spec in desired.items() if name not in existing}


def missing_subfields(existing: Dict[str, Any], desired: Dict[str, Any]) -> Dict[str, Any]:
    """Updated specs for existing top-level fields that lack some sub-fields.

    Returns ``{field: live_spec_with_the_missing_subfields_added}``. Only
    sub-fields are added; the field's own type and analyser are left exactly as
    they are live, so Elasticsearch accepts the update.
    """
    updates: Dict[str, Any] = {}
    for name, spec in desired.items():
        live = existing.get(name)
        wanted = spec.get("fields") or {}
        if not live or not wanted:
            continue
        have = live.get("fields") or {}
        new = {sub: sub_spec for sub, sub_spec in wanted.items() if sub not in have}
        if new:
            updates[name] = {**live, "fields": {**have, **new}}
    return updates


def refill_fields(document: Any, es: Any, index_name: str, names: List[str]) -> int:
    """Write the current values of ``names`` into every existing document.

    Only the given fields are sent (a partial update), computed the same way
    the document computes them when a record is saved. Records that are not in
    the index (for example ones the document never indexes) are skipped.
    Returns the number of documents updated.
    """
    doc = document()
    preparers = [(name, fn) for name, _field, fn in doc._prepared_fields if name in names]
    if not preparers:
        return 0

    def actions() -> Iterator[Dict[str, Any]]:
        for instance in doc.get_queryset().iterator(chunk_size=500):
            try:
                values = {name: fn(instance) for name, fn in preparers}
            except Exception as exc:  # one bad record must not stop the rest
                logger.warning(
                    "search_refill_skipped", index=index_name, pk=str(instance.pk), error=str(exc)
                )
                continue
            yield {
                "_op_type": "update",
                "_index": index_name,
                "_id": instance.pk,
                "doc": values,
            }

    updated, _failed = bulk(es, actions(), raise_on_error=False, stats_only=True)
    return int(updated)


class Command(BaseCommand):
    help = "Add fields and sub-fields that search documents define but their live indexes lack."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing.")

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        for document in registry.get_documents():
            index_name = document._index._name
            try:
                es = document._get_connection()
                if not es.indices.exists(index=index_name):
                    if dry_run:
                        self.stdout.write(f"{index_name}: would create the index")
                        continue
                    document._index.create(using=es)
                    self.stdout.write(self.style.SUCCESS(f"{index_name}: created the index"))
                    logger.info("search_index_created", index=index_name)
                    continue
                live = es.indices.get_mapping(index=index_name)
                existing: Dict[str, Any] = {}
                for body in live.values():  # one entry per concrete index behind an alias
                    existing.update(body.get("mappings", {}).get("properties", {}))
                desired = document._doc_type.mapping.to_dict().get("properties", {})

                fields_to_add = missing_properties(existing, desired)
                subfield_updates = missing_subfields(existing, desired)
                if not fields_to_add and not subfield_updates:
                    self.stdout.write(f"{index_name}: up to date")
                    continue

                added: List[str] = sorted(fields_to_add)
                for name, spec in subfield_updates.items():
                    have = set((existing[name].get("fields") or {}).keys())
                    added += [f"{name}.{sub}" for sub in sorted(spec["fields"]) if sub not in have]
                names = ", ".join(added)
                if dry_run:
                    self.stdout.write(
                        f"{index_name}: would add {names} and refill existing documents"
                    )
                    continue

                es.indices.put_mapping(
                    index=index_name, properties={**fields_to_add, **subfield_updates}
                )
                message = f"{index_name}: added {names}"
                if subfield_updates:
                    # Fill the new sub-fields for documents indexed before this
                    # change. Runs as a background task inside Elasticsearch.
                    task = es.update_by_query(
                        index=index_name, conflicts="proceed", wait_for_completion=False
                    )
                    message += f"; refilling existing documents (task {task.get('task')})"
                if fields_to_add:
                    count = refill_fields(document, es, index_name, sorted(fields_to_add))
                    message += f"; filled new fields in {count} existing documents"
                self.stdout.write(self.style.SUCCESS(message))
                logger.info("search_mapping_fields_added", index=index_name, fields=added)
            except Exception as exc:  # never block start-up on search problems
                self.stderr.write(f"{index_name}: could not sync mapping ({exc})")
                logger.error("search_mapping_sync_failed", index=index_name, error=str(exc))
