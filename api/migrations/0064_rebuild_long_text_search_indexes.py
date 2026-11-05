"""One-time rebuild of search indexes that still have a single-token text copy.

Long text fields (use case and collaborative summaries, descriptions, bios) had
a ``raw`` sub-field with the ``keyword`` analyzer, which turns the whole value
into one token. Elasticsearch refuses tokens over 32,766 bytes, so a long
summary failed to index: saving a published item returned an error (#266) and
every deploy failed at ``search_index --populate``. The documents no longer
define those sub-fields, but an existing index keeps its old mapping.

For each search index whose live mapping still has such a sub-field, drop it
and create it again empty with the current mapping. The deploy's release step
runs migrations first and then populates every index from the database, so
search is refilled right after. Nothing in the database changes.

Does nothing when an index is missing or already clean, and never fails the
migration: problems are only logged.
"""

import structlog
from django.conf import settings
from django.db import migrations

logger = structlog.get_logger(__name__)


def _has_single_token_text(properties):
    for field in properties.values():
        for sub in field.get("fields", {}).values():
            if sub.get("type") == "text" and sub.get("analyzer") == "keyword":
                return True
        if _has_single_token_text(field.get("properties", {})):
            return True
    return False


def rebuild_long_text_indexes(apps, schema_editor):
    try:
        from django_elasticsearch_dsl.registries import registry
        from elasticsearch_dsl.connections import connections

        es = connections.get_connection().options(request_timeout=30)
        indices = {index._name: index for index in registry.get_indices()}
        for name in set(settings.ELASTICSEARCH_INDEX_NAMES.values()):
            if not es.indices.exists(index=name):
                continue
            mappings = es.indices.get_mapping(index=name)
            if not any(
                _has_single_token_text(body.get("mappings", {}).get("properties", {}))
                for body in mappings.values()
            ):
                continue
            for concrete in mappings:
                es.indices.delete(index=concrete)
            # Create it again at once so a write from the running server cannot
            # make Elasticsearch create it with guessed field types.
            if name in indices:
                indices[name].create()
            logger.info("long_text_search_index_rebuilt", index=name)
    except Exception as exc:  # never block a deploy on search problems
        logger.error("long_text_search_index_rebuild_failed", error=str(exc))


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0063_resource_slug_not_unique"),
    ]

    operations = [
        migrations.RunPython(rebuild_long_text_indexes, migrations.RunPython.noop),
    ]
