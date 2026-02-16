from typing import Any

import structlog
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from api.models.AIModel import AIModel
from api.utils.enums import AIModelStatus
from search.documents import AIModelDocument

logger = structlog.get_logger(__name__)

INDEXABLE_STATUSES = {AIModelStatus.ACTIVE, AIModelStatus.APPROVED}


def _should_be_indexed(instance: AIModel) -> bool:
    """Return True when the AI model should exist in Elasticsearch."""
    return instance.is_public and instance.is_active and instance.status in INDEXABLE_STATUSES


@receiver(pre_save, sender=AIModel)
def handle_aimodel_visibility(sender: Any, instance: AIModel, **kwargs: Any) -> None:
    """Sync Elasticsearch document whenever publish/visibility fields change."""
    if not instance.pk:
        # New objects are handled by django-elasticsearch-dsl signal processor
        return

    try:
        original = AIModel.objects.get(pk=instance.pk)
    except AIModel.DoesNotExist:
        return

    was_indexable = _should_be_indexed(original)
    is_indexable = _should_be_indexed(instance)

    if was_indexable == is_indexable and is_indexable:
        # Still indexable, just refresh contents
        action = "update"
    elif was_indexable and not is_indexable:
        action = "delete"
    elif not was_indexable and is_indexable:
        action = "add"
    else:
        # Neither was nor is indexable; nothing to do
        return

    try:
        document = AIModelDocument.get(id=instance.id, ignore=404)
        if action == "delete":
            if document:
                document.delete()
                logger.info("Removed AI model from Elasticsearch index", model_id=instance.id)
        else:
            if document:
                document.update(instance)
            else:
                AIModelDocument().update(instance)
            logger.info(
                "Synced AI model to Elasticsearch index", model_id=instance.id, action=action
            )
    except Exception as exc:  # pragma: no cover - logging only
        logger.error(
            "Failed to sync AI model search document",
            model_id=instance.id,
            action=action,
            error=str(exc),
        )


@receiver(post_delete, sender=AIModel)
def remove_aimodel_document(sender: Any, instance: AIModel, **kwargs: Any) -> None:
    """Ensure Elasticsearch document gets deleted when the model is removed."""
    try:
        document = AIModelDocument.get(id=instance.id, ignore=404)
        if document:
            document.delete()
            logger.info("Removed deleted AI model from Elasticsearch index", model_id=instance.id)
    except Exception as exc:  # pragma: no cover - logging only
        logger.error(
            "Failed to delete AI model search document",
            model_id=instance.id,
            error=str(exc),
        )
