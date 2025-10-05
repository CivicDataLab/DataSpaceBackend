#!/usr/bin/env python
"""
Migration script to move geography data from metadata to the new geographies field.

This script:
1. Finds all datasets and usecases with geography metadata
2. Maps geography names to Geography model instances
3. Adds the geography relationships to the new ManyToMany field
4. Optionally removes the old metadata entries
5. Optionally updates the search index

Usage:
    python migrate_geography_metadata.py [--dry-run] [--remove-metadata] [--update-index] [--dataset-id ID] [--usecase-id ID] [--list-geographies]
    python migrate_geography_metadata.py [--dry-run] [--remove-metadata] [--update-index] [--datasets-only] [--usecases-only] [--list-geographies]

Options:
    --dry-run: Show what would be migrated without making changes
    --remove-metadata: Remove geography metadata after successful migration
    --update-index: Update search index after successful migration
    --dataset-id ID: Migrate only the dataset with the specified ID
    --usecase-id ID: Migrate only the usecase with the specified ID
    --datasets-only: Only migrate datasets (bulk migration)
    --usecases-only: Only migrate usecases (bulk migration)
    --list-geographies: List all available geographies in the database
"""

import argparse
import os
import subprocess
import sys
from typing import List, Set

import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DataSpace.settings")
django.setup()

from api.models import (
    Collaborative,
    Dataset,
    DatasetMetadata,
    Geography,
    Metadata,
    UseCase,
    UseCaseMetadata,
)
from api.utils.enums import MetadataModels


def parse_geography_value(value: str) -> List[str]:
    """Parse geography value which might be comma-separated."""
    if not value:
        return []
    # Split by comma and strip whitespace
    return [geo.strip() for geo in value.split(",") if geo.strip()]


def find_geography_by_name(name: str) -> Geography | None:
    """Find geography by name (case-insensitive)."""
    try:
        return Geography.objects.filter(name__iexact=name).first()
    except Geography.DoesNotExist:
        return None


def migrate_dataset_geographies(
    dry_run: bool = False, remove_metadata: bool = False, dataset_id: str | None = None
) -> None:
    """Migrate geography metadata to geographies field for datasets."""
    print("\n" + "=" * 80)
    if dataset_id:
        print(f"MIGRATING DATASET GEOGRAPHIES FOR DATASET ID: {dataset_id}")
    else:
        print("MIGRATING DATASET GEOGRAPHIES")
    print("=" * 80)

    # Get geography metadata item
    try:
        geo_metadata_item = Metadata.objects.get(
            label="Geography", model=MetadataModels.DATASET
        )
    except Metadata.DoesNotExist:
        print("⚠️  No Geography metadata item found. Skipping dataset migration.")
        return

    # Find all datasets with geography metadata
    if dataset_id:
        dataset_metadata = DatasetMetadata.objects.filter(
            metadata_item=geo_metadata_item, dataset_id=dataset_id
        ).select_related("dataset", "metadata_item")
    else:
        dataset_metadata = DatasetMetadata.objects.filter(
            metadata_item=geo_metadata_item
        ).select_related("dataset", "metadata_item")

    total_datasets = dataset_metadata.count()
    if dataset_id:
        print(
            f"\nFound {total_datasets} geography metadata entries for dataset ID {dataset_id}"
        )
    else:
        print(f"\nFound {total_datasets} datasets with geography metadata")

    migrated_count = 0
    error_count = 0
    not_found_geographies: Set[str] = set()

    for ds_meta in dataset_metadata:
        dataset = ds_meta.dataset  # type: ignore
        geo_names = parse_geography_value(ds_meta.value)  # type: ignore

        if not geo_names:
            continue

        print(f"\n📦 Dataset: {dataset.title} (ID: {dataset.id})")
        print(f"   Geography metadata: {ds_meta.value}")  # type: ignore

        geographies_to_add = []
        for geo_name in geo_names:
            geography = find_geography_by_name(geo_name)
            if geography:
                geographies_to_add.append(geography)
                print(f"   ✓ Found: {geography.name} ({geography.type})")
            else:
                not_found_geographies.add(geo_name)
                print(f"   ✗ Not found: {geo_name}")

        if geographies_to_add:
            if not dry_run:
                # Add geographies to the dataset
                dataset.geographies.add(*geographies_to_add)
                print(f"   ✅ Added {len(geographies_to_add)} geographies to dataset")

                # Optionally remove metadata
                if remove_metadata:
                    ds_meta.delete()  # type: ignore
                    print(f"   🗑️  Removed geography metadata")

                migrated_count += 1
            else:
                print(f"   [DRY RUN] Would add {len(geographies_to_add)} geographies")
        else:
            error_count += 1
            print(f"   ⚠️  No valid geographies found for this dataset")

    print(f"\n{'=' * 80}")
    if dataset_id:
        print(f"Dataset Migration Summary for Dataset ID {dataset_id}:")
    else:
        print(f"Dataset Migration Summary:")
    print(f"  Total datasets processed: {total_datasets}")
    print(f"  Successfully migrated: {migrated_count}")
    print(f"  Errors/Skipped: {error_count}")
    if not_found_geographies:
        print(f"\n  Geographies not found in database:")
        for geo in sorted(not_found_geographies):
            print(f"    - {geo}")
    print(f"{'=' * 80}")


def migrate_usecase_geographies(
    dry_run: bool = False, remove_metadata: bool = False, usecase_id: int | None = None
) -> None:
    """Migrate geography metadata to geographies field for usecases."""
    print("\n" + "=" * 80)
    if usecase_id:
        print(f"MIGRATING USECASE GEOGRAPHIES FOR USECASE ID: {usecase_id}")
    else:
        print("MIGRATING USECASE GEOGRAPHIES")
    print("=" * 80)

    # Get geography metadata item
    try:
        geo_metadata_item = Metadata.objects.get(
            label="Geography", model=MetadataModels.USECASE
        )
    except Metadata.DoesNotExist:
        print("⚠️  No Geography metadata item found. Skipping usecase migration.")
        return

    # Find all usecases with geography metadata
    if usecase_id:
        usecase_metadata = UseCaseMetadata.objects.filter(
            metadata_item=geo_metadata_item, usecase_id=str(usecase_id)
        ).select_related("usecase", "metadata_item")
    else:
        usecase_metadata = UseCaseMetadata.objects.filter(
            metadata_item=geo_metadata_item
        ).select_related("usecase", "metadata_item")

    total_usecases = usecase_metadata.count()
    if usecase_id:
        print(
            f"\nFound {total_usecases} geography metadata entries for usecase ID {usecase_id}"
        )
    else:
        print(f"\nFound {total_usecases} usecases with geography metadata")

    migrated_count = 0
    error_count = 0
    not_found_geographies: Set[str] = set()

    for uc_meta in usecase_metadata:
        usecase = uc_meta.usecase  # type: ignore
        geo_names = parse_geography_value(uc_meta.value)  # type: ignore

        if not geo_names:
            continue

        print(f"\n📋 UseCase: {usecase.title} (ID: {usecase.id})")
        print(f"   Geography metadata: {uc_meta.value}")  # type: ignore

        geographies_to_add = []
        for geo_name in geo_names:
            geography = find_geography_by_name(geo_name)
            if geography:
                geographies_to_add.append(geography)
                print(f"   ✓ Found: {geography.name} ({geography.type})")
            else:
                not_found_geographies.add(geo_name)
                print(f"   ✗ Not found: {geo_name}")

        if geographies_to_add:
            if not dry_run:
                # Add geographies to the usecase
                usecase.geographies.add(*geographies_to_add)
                print(f"   ✅ Added {len(geographies_to_add)} geographies to usecase")

                # Optionally remove metadata
                if remove_metadata:
                    uc_meta.delete()  # type: ignore
                    print(f"   🗑️  Removed geography metadata")

                migrated_count += 1
            else:
                print(f"   [DRY RUN] Would add {len(geographies_to_add)} geographies")
        else:
            error_count += 1
            print(f"   ⚠️  No valid geographies found for this usecase")

    print(f"\n{'=' * 80}")
    if usecase_id:
        print(f"UseCase Migration Summary for UseCase ID {usecase_id}:")
    else:
        print(f"UseCase Migration Summary:")
    print(f"  Total usecases processed: {total_usecases}")
    print(f"  Successfully migrated: {migrated_count}")
    print(f"  Errors/Skipped: {error_count}")
    if not_found_geographies:
        print(f"\n  Geographies not found in database:")
        for geo in sorted(not_found_geographies):
            print(f"    - {geo}")
    print(f"{'=' * 80}")


def update_search_index(index_type: str | None = None) -> None:
    """Update the Elasticsearch search index."""
    print(f"\n🔄 Updating search index{' for ' + index_type if index_type else ''}...")

    try:
        # Run the Django management command to rebuild the search index
        result = subprocess.run(
            [sys.executable, "manage.py", "search_index", "--rebuild"],
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
        )

        if result.returncode == 0:
            print("✅ Search index updated successfully!")
            if result.stdout.strip():
                print(f"Output: {result.stdout.strip()}")
        else:
            print("❌ Failed to update search index!")
            if result.stderr.strip():
                print(f"Error: {result.stderr.strip()}")

    except Exception as e:
        print(f"❌ Error updating search index: {str(e)}")


def list_available_geographies() -> None:
    """List all available geographies in the database."""
    print("\n" + "=" * 80)
    print("AVAILABLE GEOGRAPHIES IN DATABASE")
    print("=" * 80)

    geographies = Geography.objects.all().order_by("type", "name")

    if not geographies.exists():
        print("\n⚠️  No geographies found in database!")
        print("   Please populate geographies first using:")
        print("   python manage.py populate_geographies")
        return

    by_type: dict[str, list] = {}
    for geo in geographies:
        if geo.type not in by_type:  # type: ignore
            by_type[geo.type] = []  # type: ignore
        by_type[geo.type].append(geo)  # type: ignore

    for geo_type, geos in sorted(by_type.items()):
        print(f"\n{geo_type}:")
        for geo in geos:
            parent_info = f" (parent: {geo.parent_id.name})" if geo.parent_id else ""  # type: ignore
            print(f"  - {geo.name}{parent_info}")  # type: ignore

    print(f"\nTotal: {geographies.count()} geographies")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate geography metadata to geographies field"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    parser.add_argument(
        "--remove-metadata",
        action="store_true",
        help="Remove geography metadata after successful migration",
    )
    parser.add_argument(
        "--list-geographies",
        action="store_true",
        help="List all available geographies in the database",
    )
    parser.add_argument(
        "--datasets-only",
        action="store_true",
        help="Only migrate datasets",
    )
    parser.add_argument(
        "--usecases-only",
        action="store_true",
        help="Only migrate usecases",
    )
    parser.add_argument(
        "--update-index",
        action="store_true",
        help="Update search index after successful migration",
    )
    parser.add_argument(
        "--dataset-id",
        type=str,
        help="Migrate only the dataset with the specified ID (UUID)",
    )
    parser.add_argument(
        "--usecase-id",
        type=int,
        help="Migrate only the usecase with the specified ID",
    )

    args = parser.parse_args()

    if args.list_geographies:
        list_available_geographies()
        return

    # Validate arguments
    if args.dataset_id and args.usecase_id:
        print("❌ Error: Cannot specify both --dataset-id and --usecase-id")
        sys.exit(1)

    if args.dataset_id and (args.datasets_only or args.usecases_only):
        print(
            "❌ Error: Cannot use --dataset-id with --datasets-only or --usecases-only"
        )
        sys.exit(1)

    if args.usecase_id and (args.datasets_only or args.usecases_only):
        print(
            "❌ Error: Cannot use --usecase-id with --datasets-only or --usecases-only"
        )
        sys.exit(1)

    print("\n" + "=" * 80)
    print("GEOGRAPHY METADATA MIGRATION SCRIPT")
    print("=" * 80)

    if args.dry_run:
        print("\n🔍 DRY RUN MODE - No changes will be made")

    if args.remove_metadata and not args.dry_run:
        print("\n⚠️  WARNING: Geography metadata will be DELETED after migration")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("Migration cancelled.")
            return

    # Run migrations
    if args.dataset_id:
        migrate_dataset_geographies(
            dry_run=args.dry_run,
            remove_metadata=args.remove_metadata,
            dataset_id=args.dataset_id,
        )
    elif args.usecase_id:
        migrate_usecase_geographies(
            dry_run=args.dry_run,
            remove_metadata=args.remove_metadata,
            usecase_id=args.usecase_id,
        )
    else:
        # Bulk migration mode
        if not args.usecases_only:
            migrate_dataset_geographies(
                dry_run=args.dry_run, remove_metadata=args.remove_metadata
            )

        if not args.datasets_only:
            migrate_usecase_geographies(
                dry_run=args.dry_run, remove_metadata=args.remove_metadata
            )

    print("\n" + "=" * 80)
    print("MIGRATION COMPLETE")
    print("=" * 80)

    if args.dry_run:
        print("\n💡 This was a dry run. Run without --dry-run to apply changes.")
    else:
        print("\n✅ Migration completed successfully!")

        # Update search index if requested and migration was successful
        if args.update_index:
            # Determine which index type to update based on what was migrated
            if args.dataset_id:
                update_search_index("datasets")
            elif args.usecase_id:
                update_search_index("usecases")
            else:
                # For bulk migrations, update based on what was actually migrated
                if not args.usecases_only:
                    update_search_index("datasets")
                if not args.datasets_only:
                    update_search_index("usecases")

        print("\n📝 Next steps:")
        print("   1. Verify the migrated data in the admin panel")
        if not args.update_index:
            print(
                "   2. Re-index Elasticsearch: python manage.py search_index --rebuild"
            )
        print("   3. Test the geography filters in the frontend")


if __name__ == "__main__":
    main()
