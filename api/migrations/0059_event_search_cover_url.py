"""Add ``cover_url`` to a live ``event`` search index. Touches Elasticsearch only.

The deploy's release step refills every index right after ``migrate`` and
before ``sync_search_mappings`` runs. Without this step Elasticsearch would
guess the type of the new ``cover_url`` field on the first refilled document.
Does nothing when the index is missing (the release step then creates it with
the full mapping), and never fails the migration: problems are only logged.
"""

import structlog
from django.conf import settings
from django.db import migrations

logger = structlog.get_logger(__name__)


def add_cover_url_field(apps, schema_editor):
    try:
        from elasticsearch_dsl.connections import connections

        index_name = settings.ELASTICSEARCH_INDEX_NAMES["search.documents.event_document"]
        es = connections.get_connection().options(request_timeout=10)
        if es.indices.exists(index=index_name):
            es.indices.put_mapping(
                index=index_name,
                properties={"cover_url": {"type": "keyword", "index": False}},
            )
    except Exception as exc:  # never block a deploy on search problems
        logger.error("event_cover_mapping_failed", error=str(exc))


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0058_file_field_storages"),
    ]

    operations = [
        migrations.RunPython(add_cover_url_field, migrations.RunPython.noop),
    ]
