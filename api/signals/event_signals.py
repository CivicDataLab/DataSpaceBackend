"""
event_signals
─────────────
Keep search honest: publishing an event adds it to the index, unpublishing or
deleting it removes it, so a draft is never searchable. Each index write is
followed by a search-cache bump so listings do not serve stale pages.
"""

from typing import Any

import structlog
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from api.models import Event
from api.utils.enums import EventStatus
from api.utils.search_cache import invalidate_search_cache
from search.documents import EventDocument

logger = structlog.getLogger(__name__)


def _should_be_indexed(instance: Event) -> bool:
    """An event belongs in search only while it is PUBLISHED."""
    return instance.status == EventStatus.PUBLISHED.value


@receiver(pre_save, sender=Event)
def handle_event_visibility(sender: Any, instance: Event, **kwargs: Any) -> None:
    """Add / refresh / drop the search document as an event is published or not.

    New rows are handled by the django-elasticsearch-dsl signal processor. ES
    errors are logged and swallowed — indexing is best-effort and a rebuild
    reconciles it.
    """
    if not instance.pk:
        return

    try:
        original = Event.objects.get(pk=instance.pk)
    except Event.DoesNotExist:
        return

    was_indexable = _should_be_indexed(original)
    is_indexable = _should_be_indexed(instance)

    if was_indexable and is_indexable:
        action = "update"
    elif was_indexable and not is_indexable:
        action = "delete"
    elif not was_indexable and is_indexable:
        action = "add"
    else:
        return

    try:
        document = EventDocument.get(id=instance.id, ignore=404)
        if action == "delete":
            if document:
                document.delete(refresh=True)
                logger.info("event removed from search index", event_id=str(instance.id))
        else:
            EventDocument().update(instance, refresh=True)
            logger.info("event synced to search index", event_id=str(instance.id), action=action)
        # After the index write, never before it: see invalidate_search_cache.
        invalidate_search_cache()
    except Exception as exc:  # pragma: no cover - logging only
        logger.error(
            "failed to sync event search document",
            event_id=str(instance.id),
            action=action,
            error=str(exc),
        )


@receiver(post_delete, sender=Event)
def remove_event_document(sender: Any, instance: Event, **kwargs: Any) -> None:
    """Drop the search document when an event is deleted."""
    try:
        document = EventDocument.get(id=instance.id, ignore=404)
        if document:
            document.delete(refresh=True)
            logger.info("deleted event removed from search index", event_id=str(instance.id))
            invalidate_search_cache()
    except Exception as exc:  # pragma: no cover - logging only
        logger.error(
            "failed to delete event search document",
            event_id=str(instance.id),
            error=str(exc),
        )
