from typing import Any

import structlog
from django.core.cache import cache
from django.db.models.signals import pre_save
from django.dispatch import receiver

from api.models.Collaborative import Collaborative
from api.utils.enums import CollaborativeStatus
from search.documents import CollaborativeDocument

from .dataset_signals import SEARCH_CACHE_VERSION_KEY

logger = structlog.get_logger(__name__)


@receiver(pre_save, sender=Collaborative)
def handle_collaborative_publication(sender: Any, instance: Collaborative, **kwargs: Any) -> None:
    """Sync Elasticsearch index when collaborative publication state changes."""

    try:
        if not instance.pk:
            return

        original = Collaborative.objects.get(pk=instance.pk)

        status_changing_to_published = (
            original.status != CollaborativeStatus.PUBLISHED
            and instance.status == CollaborativeStatus.PUBLISHED
        )
        status_changing_from_published = (
            original.status == CollaborativeStatus.PUBLISHED
            and instance.status != CollaborativeStatus.PUBLISHED
        )
        remains_published = (
            original.status == CollaborativeStatus.PUBLISHED
            and instance.status == CollaborativeStatus.PUBLISHED
        )

        if status_changing_to_published or status_changing_from_published:
            version = cache.get(SEARCH_CACHE_VERSION_KEY, 0)
            cache.set(SEARCH_CACHE_VERSION_KEY, version + 1)
            logger.info("Invalidated search cache for collaborative", collaborative_id=instance.id)

        if status_changing_from_published:
            document = CollaborativeDocument.get(id=instance.id, ignore=404)
            if document:
                document.delete()
                logger.info(
                    "Removed collaborative from Elasticsearch index",
                    collaborative_id=instance.id,
                )
        elif status_changing_to_published or remains_published:
            document = CollaborativeDocument.get(id=instance.id, ignore=404)
            if document:
                document.update(instance)
            else:
                CollaborativeDocument().update(instance)
            logger.info(
                "Synced collaborative to Elasticsearch index",
                collaborative_id=instance.id,
            )

    except Exception as exc:  # pragma: no cover - logging only
        logger.error(
            "Error in collaborative publication signal handler",
            collaborative_id=getattr(instance, "id", None),
            error=str(exc),
        )
        # Avoid raising to prevent save failures
