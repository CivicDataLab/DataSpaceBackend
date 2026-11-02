"""One-time repair of the ``event`` search index. Touches Elasticsearch only.

The first deploy with event search populated the index before it was created
(``api.Event`` was missing from the create list in scripts/ci-deploy.sh, fixed
since), so Elasticsearch created it with guessed field types and every event
search failed. If the live index has such a guessed mapping (``status`` not a
keyword), drop it: the deploy's release step runs migrations first, then
creates each search index and populates it, so the next steps rebuild it with
the real mapping and refill it from the database.

Does nothing when the index is missing or already correct, and never fails the
migration: problems are only logged.
"""

import structlog
from django.conf import settings
from django.db import migrations

logger = structlog.get_logger(__name__)


def drop_guessed_event_index(apps, schema_editor):
    try:
        from elasticsearch_dsl.connections import connections

        index_name = settings.ELASTICSEARCH_INDEX_NAMES["search.documents.event_document"]
        es = connections.get_connection().options(request_timeout=10)
        if not es.indices.exists(index=index_name):
            return
        for concrete, body in es.indices.get_mapping(index=index_name).items():
            status = body.get("mappings", {}).get("properties", {}).get("status", {})
            if status.get("type") != "keyword":
                es.indices.delete(index=concrete)
                logger.info("guessed_event_index_dropped", index=concrete)
    except Exception as exc:  # never block a deploy on search problems
        logger.error("event_index_repair_failed", error=str(exc))


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0056_update_license_choices"),
    ]

    operations = [
        migrations.RunPython(drop_guessed_event_index, migrations.RunPython.noop),
    ]
