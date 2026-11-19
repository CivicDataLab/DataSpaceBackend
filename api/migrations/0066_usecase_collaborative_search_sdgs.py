"""Add ``sdgs`` to live ``usecase`` and ``collaborative`` search indexes. Touches
Elasticsearch only.

The deploy's release step refills every index right after ``migrate`` and
before ``sync_search_mappings`` runs. Without this step Elasticsearch would
guess ``text`` for the new ``sdgs`` field on the first refilled document, and
the ``sdgs`` facet in unified search would then fail every search with a 400.
Does nothing for a missing index (the release step then creates it with the
full mapping), and never fails the migration: problems are only logged.
"""

import structlog
from django.conf import settings
from django.db import migrations

logger = structlog.get_logger(__name__)

DOCUMENT_MODULES = [
    "search.documents.usecase_document",
    "search.documents.collaborative_document",
]


def add_sdgs_field(apps, schema_editor):
    from elasticsearch_dsl.connections import connections

    for module in DOCUMENT_MODULES:
        try:
            index_name = settings.ELASTICSEARCH_INDEX_NAMES[module]
            es = connections.get_connection().options(request_timeout=10)
            if es.indices.exists(index=index_name):
                es.indices.put_mapping(index=index_name, properties={"sdgs": {"type": "keyword"}})
        except Exception as exc:  # never block a deploy on search problems
            logger.error("sdgs_search_mapping_failed", document=module, error=str(exc))


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0065_merge_search_hotfix"),
    ]

    operations = [
        migrations.RunPython(add_sdgs_field, migrations.RunPython.noop),
    ]
