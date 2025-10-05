"""
Management command to clean up orphaned metadata records.

This command removes DatasetMetadata and UseCaseMetadata records
that reference non-existent Metadata items.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Q

from api.models import DatasetMetadata, UseCaseMetadata


class Command(BaseCommand):
    help = "Clean up orphaned metadata records that reference deleted Metadata items"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made\n")
            )

        # Find orphaned DatasetMetadata records
        orphaned_dataset_metadata = DatasetMetadata.objects.filter(
            metadata_item__isnull=True
        )
        dataset_count = orphaned_dataset_metadata.count()

        # Find orphaned UseCaseMetadata records
        orphaned_usecase_metadata = UseCaseMetadata.objects.filter(
            metadata_item__isnull=True
        )
        usecase_count = orphaned_usecase_metadata.count()

        total_count = dataset_count + usecase_count

        if total_count == 0:
            self.stdout.write(
                self.style.SUCCESS("✓ No orphaned metadata records found")
            )
            return

        self.stdout.write(
            self.style.WARNING(f"Found {total_count} orphaned metadata record(s):")
        )
        self.stdout.write(f"  - DatasetMetadata: {dataset_count}")
        self.stdout.write(f"  - UseCaseMetadata: {usecase_count}\n")

        if dry_run:
            # Show details of what would be deleted
            if dataset_count > 0:
                self.stdout.write("DatasetMetadata records that would be deleted:")
                for meta in orphaned_dataset_metadata[:10]:  # Show first 10
                    self.stdout.write(
                        f"  - ID: {meta.id}, Dataset: {meta.dataset.title}, Value: {meta.value}"  # type: ignore
                    )
                if dataset_count > 10:
                    self.stdout.write(f"  ... and {dataset_count - 10} more")

            if usecase_count > 0:
                self.stdout.write("\nUseCaseMetadata records that would be deleted:")
                for meta in orphaned_usecase_metadata[:10]:  # Show first 10
                    self.stdout.write(
                        f"  - ID: {meta.id}, UseCase: {meta.usecase.title}, Value: {meta.value}"  # type: ignore
                    )
                if usecase_count > 10:
                    self.stdout.write(f"  ... and {usecase_count - 10} more")

            self.stdout.write(
                self.style.WARNING(
                    f"\nRun without --dry-run to delete these {total_count} record(s)"
                )
            )
        else:
            # Actually delete the records
            deleted_dataset = orphaned_dataset_metadata.delete()
            deleted_usecase = orphaned_usecase_metadata.delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Successfully deleted {total_count} orphaned metadata record(s)"
                )
            )
            self.stdout.write(f"  - DatasetMetadata: {deleted_dataset[0]}")
            self.stdout.write(f"  - UseCaseMetadata: {deleted_usecase[0]}")
