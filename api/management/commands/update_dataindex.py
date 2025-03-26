import time
import uuid
from typing import Any, Dict, List, Optional, cast

import structlog
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from api.models.Resource import Resource, ResourceDataTable
from api.utils.data_indexing import index_resource_data

logger = structlog.get_logger("dataspace.commands.update_dataindex")


class Command(BaseCommand):
    help = "Update dataindex (ResourceDataTable) for all resources"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--resource-id",
            type=str,
            help="Update dataindex for a specific resource by ID",
            required=False,
            default="",
        )
        parser.add_argument(
            "--dataset-id",
            type=str,
            help="Update dataindex for all resources in a specific dataset by ID",
            required=False,
            default="",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip resources that already have a dataindex",
        )

    def handle(self, *args: Any, **options: Dict[str, Any]) -> None:
        resource_id_str: str = str(options.get("resource_id", ""))
        dataset_id_str: str = str(options.get("dataset_id", ""))
        skip_existing = options.get("skip_existing")

        # Convert string IDs to UUID objects if provided
        resource_id: Optional[uuid.UUID] = None
        dataset_id: Optional[uuid.UUID] = None

        # Only try to convert valid UUID strings
        if resource_id_str and resource_id_str.strip():
            try:
                resource_id = uuid.UUID(resource_id_str)
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(
                        f"Invalid UUID format for resource-id: {resource_id_str}"
                    )
                )
                return

        if dataset_id_str and dataset_id_str.strip():
            try:
                dataset_id = uuid.UUID(dataset_id_str)
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(
                        f"Invalid UUID format for dataset-id: {dataset_id_str}"
                    )
                )
                return

        start_time = time.time()
        success_count = 0
        error_count = 0
        skipped_count = 0

        # Filter resources based on command arguments
        resources = Resource.objects.all()

        if resource_id:
            resources = resources.filter(id=resource_id)
            self.stdout.write(f"Processing single resource with ID: {resource_id}")
        elif dataset_id:
            resources = resources.filter(dataset_id=dataset_id)
            self.stdout.write(f"Processing resources for dataset with ID: {dataset_id}")
        else:
            self.stdout.write("Processing all resources")

        total_resources = resources.count()
        self.stdout.write(f"Found {total_resources} resources to process")

        # Process each resource
        for i, resource in enumerate(resources, 1):
            # Cast resource to the proper type for type checking
            resource = cast(Resource, resource)

            try:
                # Skip resources that don't have file details
                if not hasattr(resource, "resourcefiledetails"):
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{i}/{total_resources}] Skipping resource {resource.id} - No file details"
                        )
                    )
                    skipped_count += 1
                    continue

                # Skip resources that aren't CSV files
                file_details = resource.resourcefiledetails
                if not file_details or not file_details.format.lower() == "csv":
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{i}/{total_resources}] Skipping resource {resource.id} - Not a CSV file"
                        )
                    )
                    skipped_count += 1
                    continue

                # Skip resources that already have a dataindex if skip_existing is True
                if skip_existing and hasattr(resource, "resourcedatatable"):
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{i}/{total_resources}] Skipping resource {resource.id} - Already has dataindex"
                        )
                    )
                    skipped_count += 1
                    continue

                self.stdout.write(
                    f"[{i}/{total_resources}] Processing resource {resource.id} - {resource.name}"
                )

                # Update dataindex for the resource
                with transaction.atomic():
                    data_table = index_resource_data(resource)

                if data_table:
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[{i}/{total_resources}] Successfully updated dataindex for resource {resource.id}"
                        )
                    )
                else:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"[{i}/{total_resources}] Failed to update dataindex for resource {resource.id}"
                        )
                    )
            except Exception as e:
                error_count += 1
                logger.error(
                    f"Error updating dataindex for resource {resource.id}",
                    error=str(e),
                    exc_info=True,
                )
                self.stdout.write(
                    self.style.ERROR(
                        f"[{i}/{total_resources}] Error updating dataindex for resource {resource.id}: {str(e)}"
                    )
                )

        # Print summary
        elapsed_time = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDataindex update completed in {elapsed_time:.2f} seconds"
            )
        )
        self.stdout.write(f"Total resources processed: {total_resources}")
        self.stdout.write(f"Successful updates: {success_count}")
        self.stdout.write(f"Failed updates: {error_count}")
        self.stdout.write(f"Skipped resources: {skipped_count}")
