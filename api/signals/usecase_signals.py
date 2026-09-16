from typing import Any

import structlog
from django.db.models.signals import pre_save
from django.dispatch import receiver

from api.models.UseCase import UseCase
from api.utils.enums import UseCaseStatus
from api.utils.search_cache import invalidate_search_cache
from search.documents.usecase_document import UseCaseDocument

logger = structlog.getLogger(__name__)


@receiver(pre_save, sender=UseCase)
def handle_usecase_publication(sender: Any, instance: UseCase, **kwargs: Any) -> None:
    """
    Signal handler for usecase publication state changes.

    This will:
    1. Update the Elasticsearch index when status changes to/from PUBLISHED
    2. Invalidate search cache when status changes
    """
    try:
        # Check if this is an existing usecase (not a new one)
        if instance.pk:
            # Get the original usecase from the database
            original = UseCase.objects.get(pk=instance.pk)

            # Check if status is changing to/from PUBLISHED
            status_changing_to_published = (
                original.status != UseCaseStatus.PUBLISHED
                and instance.status == UseCaseStatus.PUBLISHED
            )
            status_changing_from_published = (
                original.status == UseCaseStatus.PUBLISHED
                and instance.status != UseCaseStatus.PUBLISHED
            )

            # Only proceed if status is actually changing
            if status_changing_to_published or status_changing_from_published:
                # Update Elasticsearch index
                if status_changing_from_published:
                    # Remove from index when unpublished
                    try:
                        document = UseCaseDocument.get(id=instance.id, ignore=404)
                        if document:
                            document.delete(refresh=True)
                            logger.info(
                                f"Removed usecase {instance.title} from Elasticsearch index"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to delete Elasticsearch document for usecase {instance.title}: {str(e)}"
                        )
                elif status_changing_to_published:
                    # Add to index when published
                    try:
                        document = UseCaseDocument()
                        document.update(instance, refresh=True)
                        logger.info(
                            f"Added usecase {instance.title} to Elasticsearch index"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to add Elasticsearch document for usecase {instance.title}: {str(e)}"
                        )

                # After the index write, never before it: see invalidate_search_cache.
                try:
                    invalidate_search_cache()
                    logger.info(f"Invalidated search cache for usecase {instance.title}")
                except Exception as e:
                    logger.error(f"Failed to invalidate search cache: {str(e)}")

    except Exception as e:
        logger.error(f"Error in usecase publication signal handler: {str(e)}")
        # Don't raise the exception to avoid blocking the save operation
