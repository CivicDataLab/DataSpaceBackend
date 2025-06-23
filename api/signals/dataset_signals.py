from typing import Any, Optional

import structlog
from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import pre_save
from django.dispatch import receiver

from api.managers.dvc_manager import DVCManager
from api.models.Dataset import Dataset
from api.models.Resource import Resource, ResourceVersion, _increment_version
from api.utils.enums import DatasetStatus
from search.documents.dataset_document import DatasetDocument

# Cache version key for search results
SEARCH_CACHE_VERSION_KEY = "search_results_version"

logger = structlog.getLogger(__name__)


@receiver(pre_save, sender=Dataset)
def handle_dataset_publication(sender: Any, instance: Dataset, **kwargs: Any) -> None:
    """
    Signal handler for dataset publication state changes.

    This will:
    1. Trigger a minor version increment for all resources when status changes from DRAFT to PUBLISHED
    2. Update the Elasticsearch index when status changes to/from PUBLISHED
    """
    try:
        # Check if this is an existing dataset (not a new one)
        if instance.pk:
            # Get the original dataset from the database
            original = Dataset.objects.get(pk=instance.pk)

            # Check if status is changing to/from PUBLISHED
            status_changing_to_published = (
                original.status != DatasetStatus.PUBLISHED
                and instance.status == DatasetStatus.PUBLISHED
            )
            status_changing_from_published = (
                original.status == DatasetStatus.PUBLISHED
                and instance.status != DatasetStatus.PUBLISHED
            )

            # Invalidate search results cache by incrementing version
            try:
                version = cache.get(SEARCH_CACHE_VERSION_KEY, 0)
                cache.set(SEARCH_CACHE_VERSION_KEY, version + 1)
                logger.info(f"Invalidated search cache for dataset {instance.title}")
            except Exception as e:
                logger.error(f"Failed to invalidate search cache: {str(e)}")

            # Update Elasticsearch index
            if status_changing_from_published:
                try:
                    document = DatasetDocument.get(id=instance.id, ignore=404)
                    document.delete()
                except Exception as e:
                    logger.error(
                        f"Failed to delete Elasticsearch document for dataset {instance.title}: {str(e)}"
                    )
            else:
                try:
                    document = DatasetDocument.get(id=instance.id, ignore=404)
                    if document:
                        document.update(instance)
                    else:
                        DatasetDocument().update(instance)
                except Exception as e:
                    logger.error(
                        f"Failed to update Elasticsearch document for dataset {instance.title}: {str(e)}"
                    )

            # Handle resource version increments for publication
            if status_changing_to_published:
                logger.info(
                    f"Dataset {instance.title} is being published, incrementing resource versions"
                )

                # Get all resources for this dataset
                resources = instance.resources.all()

                # Initialize DVC manager
                dvc = DVCManager(settings.DVC_REPO_PATH)

                # Increment version for each resource
                for resource in resources:  # type: Resource
                    try:
                        # Get the latest version
                        last_version: Optional[ResourceVersion] = (
                            resource.versions.order_by("-created_at").first()
                        )

                        if last_version:
                            # Increment minor version (publication is a significant change)
                            new_version = _increment_version(
                                last_version.version_number, increment_type="minor"
                            )

                            # Get the resource file path
                            file_path: str = resource.resourcefiledetails.file.path

                            # Track with DVC
                            dvc_file = dvc.track_resource(file_path)
                            message: str = (
                                f"Publishing resource: {resource.name} to version {new_version}"
                            )
                            dvc.commit_version(dvc_file, message)
                            dvc.tag_version(f"{resource.name}-{new_version}")

                            # Create version record
                            ResourceVersion.objects.create(
                                resource=resource,
                                version_number=new_version,
                                change_description=f"Version created due to dataset publication",
                            )

                            # Update resource version field
                            resource.version = new_version
                            resource.save(update_fields=["version"])

                            logger.info(
                                f"Incremented version for resource {resource.name} to {new_version}"
                            )
                        else:
                            logger.warning(
                                f"No previous version found for resource {resource.name}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to increment version for resource {resource.name}: {str(e)}"
                        )
    except Exception as e:
        logger.error(f"Error in dataset publication signal handler: {str(e)}")
        # Don't raise the exception to avoid blocking the save operation
