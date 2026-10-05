"""Add new fields to existing Elasticsearch indexes without rebuilding them.

Deploys never rebuild or re-map indexes. When a search document gains a field
(e.g. ``source_platform`` on datasets), an index created before that change
does not know it. The first document that carries a string value then gets the
field dynamically mapped as ``text``, and any ``terms`` aggregation or filter
on it fails with "Fielddata is disabled" for every search.

This command compares each registered document's mapping with its live index
and adds only the top-level fields the index is missing (Elasticsearch allows
adding fields to an existing mapping; it does not allow changing them). It
never deletes or reindexes anything, skips indexes that do not exist yet
(those are created with the full mapping on first use), and never fails the
process: problems are logged and reported, so a search outage cannot stop the
backend from starting.

    python manage.py sync_search_mappings            # apply
    python manage.py sync_search_mappings --dry-run  # report only

Runs from docker-entrypoint.sh after migrations.
"""

from __future__ import annotations

from typing import Any, Dict

import structlog
from django.core.management.base import BaseCommand
from django_elasticsearch_dsl.registries import registry

logger = structlog.get_logger("dataspace.search_mappings")


def missing_properties(existing: Dict[str, Any], desired: Dict[str, Any]) -> Dict[str, Any]:
    """Top-level fields present in ``desired`` but absent from ``existing``."""
    return {name: spec for name, spec in desired.items() if name not in existing}


class Command(BaseCommand):
    help = "Add fields that search documents define but their live indexes lack."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing.")

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        for document in registry.get_documents():
            index_name = document._index._name
            try:
                es = document._get_connection()
                if not es.indices.exists(index=index_name):
                    self.stdout.write(f"{index_name}: no index yet, skipped")
                    continue
                live = es.indices.get_mapping(index=index_name)
                existing: Dict[str, Any] = {}
                for body in live.values():  # one entry per concrete index behind an alias
                    existing.update(body.get("mappings", {}).get("properties", {}))
                desired = document._doc_type.mapping.to_dict().get("properties", {})
                missing = missing_properties(existing, desired)
                if not missing:
                    self.stdout.write(f"{index_name}: up to date")
                    continue
                names = ", ".join(sorted(missing))
                if dry_run:
                    self.stdout.write(f"{index_name}: would add {names}")
                    continue
                es.indices.put_mapping(index=index_name, properties=missing)
                self.stdout.write(self.style.SUCCESS(f"{index_name}: added {names}"))
                logger.info("search_mapping_fields_added", index=index_name, fields=sorted(missing))
            except Exception as exc:  # never block start-up on search problems
                self.stderr.write(f"{index_name}: could not sync mapping ({exc})")
                logger.error("search_mapping_sync_failed", index=index_name, error=str(exc))
