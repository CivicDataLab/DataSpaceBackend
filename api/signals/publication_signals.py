"""
publication_signals
────────────────────
Keeps a Resource's stored files from leaking. When a content block is deleted —
directly, or by the FK cascade when its parent publication is deleted — its file
is removed from disk. (Django's ORM never deletes the underlying file on its
own, so ``Resource`` today leaks files on delete; we intentionally don't repeat
that here.)
"""

from typing import Any

import structlog
from django.db.models.signals import post_delete
from django.dispatch import receiver

from api.models import PublicationBlock

logger = structlog.getLogger(__name__)


@receiver(post_delete, sender=PublicationBlock)
def remove_publication_block_file(sender: Any, instance: PublicationBlock, **kwargs: Any) -> None:
    """Delete a removed block's file from storage."""
    if instance.file:
        instance.file.delete(save=False)
        logger.info("publication block file removed", block_id=str(instance.id))
