"""
publication_signals
────────────────────
Two jobs. First, keep a Resource's stored files from leaking: when a content
block is deleted — directly, or by the FK cascade when its parent publication is
deleted — its file is removed from disk. Second, keep search honest: publishing
a resource adds it to the index, unpublishing or deleting it removes it, so a
draft is never searchable. (Django's ORM never deletes a file on its own, so
``Resource`` today leaks files on delete; we intentionally don't repeat that.)
"""

from typing import Any

import structlog
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from api.models import Publication, PublicationBlock
from api.utils.enums import PublicationStatus
from search.documents import PublicationDocument

logger = structlog.getLogger(__name__)


@receiver(post_delete, sender=PublicationBlock)
def remove_publication_block_file(sender: Any, instance: PublicationBlock, **kwargs: Any) -> None:
    """Delete a removed block's file from storage."""
    if instance.file:
        instance.file.delete(save=False)
        logger.info("publication block file removed", block_id=str(instance.id))


def _should_be_indexed(instance: Publication) -> bool:
    """A resource belongs in search only while it is PUBLISHED."""
    return instance.status == PublicationStatus.PUBLISHED.value


@receiver(pre_save, sender=Publication)
def handle_publication_visibility(sender: Any, instance: Publication, **kwargs: Any) -> None:
    """Add / refresh / drop the search document as a resource is published or not.

    New rows are handled by the django-elasticsearch-dsl signal processor. ES
    errors are logged and swallowed — indexing is best-effort and a rebuild
    reconciles it.
    """
    if not instance.pk:
        return

    try:
        original = Publication.objects.get(pk=instance.pk)
    except Publication.DoesNotExist:
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
        document = PublicationDocument.get(id=instance.id, ignore=404)
        if action == "delete":
            if document:
                document.delete()
                logger.info("resource removed from search index", publication_id=str(instance.id))
        else:
            if document:
                document.update(instance)
            else:
                PublicationDocument().update(instance)
            logger.info(
                "resource synced to search index",
                publication_id=str(instance.id),
                action=action,
            )
    except Exception as exc:  # pragma: no cover - logging only
        logger.error(
            "failed to sync resource search document",
            publication_id=str(instance.id),
            action=action,
            error=str(exc),
        )


@receiver(post_delete, sender=Publication)
def remove_publication_document(sender: Any, instance: Publication, **kwargs: Any) -> None:
    """Drop the search document when a resource is deleted."""
    try:
        document = PublicationDocument.get(id=instance.id, ignore=404)
        if document:
            document.delete()
            logger.info(
                "deleted resource removed from search index",
                publication_id=str(instance.id),
            )
    except Exception as exc:  # pragma: no cover - logging only
        logger.error(
            "failed to delete resource search document",
            publication_id=str(instance.id),
            error=str(exc),
        )
