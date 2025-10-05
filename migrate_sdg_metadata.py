#!/usr/bin/env python
"""
Migration script to move SDG data from metadata to the new sdgs field.

This script:
1. Finds all usecases with SDG metadata
2. Maps SDG codes/names to SDG model instances
3. Adds the SDG relationships to the new ManyToMany field
4. Optionally removes the old metadata entries
5. Optionally updates the search index

Usage:
    python migrate_sdg_metadata.py [--dry-run] [--remove-metadata] [--update-index] [--usecase-id ID] [--list-sdgs]

Options:
    --dry-run: Show what would be migrated without making changes
    --remove-metadata: Remove SDG metadata after successful migration
    --update-index: Update search index after successful migration
    --usecase-id ID: Migrate only the usecase with the specified ID
    --list-sdgs: List all available SDGs in the database
"""

import argparse
import os
import subprocess
import sys
from typing import List, Set

import django

from api.utils.enums import MetadataModels

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DataSpace.settings")
django.setup()

from api.models import SDG, Metadata, UseCase, UseCaseMetadata


def parse_sdg_value(value: str) -> List[str]:
    """Parse SDG value which might be comma-separated."""
    if not value:
        return []
    # Split by comma and strip whitespace
    return [sdg.strip() for sdg in value.split(",") if sdg.strip()]


def find_sdg_by_code_or_name(identifier: str) -> SDG | None:
    """Find SDG by code or name (case-insensitive)."""
    try:
        # Try to find by code first (e.g., "SDG1", "SDG 1", "1")
        # Normalize the identifier
        normalized = identifier.upper().replace(" ", "")
        if not normalized.startswith("SDG"):
            normalized = f"SDG{normalized}"

        sdg = SDG.objects.filter(code__iexact=normalized).first()
        if sdg:
            return sdg

        # If not found by code, try by name
        return SDG.objects.filter(name__icontains=identifier).first()
    except SDG.DoesNotExist:
        return None


def migrate_usecase_sdgs(
    dry_run: bool = False, remove_metadata: bool = False, usecase_id: int | None = None
) -> None:
    """Migrate SDG metadata to sdgs field for usecases."""
    print("\n" + "=" * 80)
    if usecase_id:
        print(f"MIGRATING USECASE SDGS FOR USECASE ID: {usecase_id}")
    else:
        print("MIGRATING USECASE SDGS")
    print("=" * 80)

    # Get SDG metadata item
    try:
        sdg_metadata_item = Metadata.objects.get(
            label="SDG Goal", model=MetadataModels.USECASE
        )
    except Metadata.DoesNotExist:
        print("⚠️  No SDG metadata item found. Skipping usecase migration.")
        return

    # Find all usecases with SDG metadata
    if usecase_id:
        usecase_metadata = UseCaseMetadata.objects.filter(
            metadata_item=sdg_metadata_item, usecase_id=str(usecase_id)
        ).select_related("usecase", "metadata_item")
    else:
        usecase_metadata = UseCaseMetadata.objects.filter(
            metadata_item=sdg_metadata_item
        ).select_related("usecase", "metadata_item")

    total_usecases = usecase_metadata.count()
    if usecase_id:
        print(
            f"\nFound {total_usecases} SDG metadata entries for usecase ID {usecase_id}"
        )
    else:
        print(f"\nFound {total_usecases} usecases with SDG metadata")

    migrated_count = 0
    error_count = 0
    not_found_sdgs: Set[str] = set()

    for uc_meta in usecase_metadata:
        usecase = uc_meta.usecase  # type: ignore
        sdg_identifiers = parse_sdg_value(uc_meta.value)  # type: ignore

        if not sdg_identifiers:
            continue

        print(f"\n📋 UseCase: {usecase.title} (ID: {usecase.id})")
        print(f"   SDG metadata: {uc_meta.value}")  # type: ignore

        sdgs_to_add = []
        for sdg_id in sdg_identifiers:
            sdg = find_sdg_by_code_or_name(sdg_id)
            if sdg:
                sdgs_to_add.append(sdg)
                print(f"   ✓ Found: {sdg.code} - {sdg.name}")  # type: ignore
            else:
                not_found_sdgs.add(sdg_id)
                print(f"   ✗ Not found: {sdg_id}")

        if sdgs_to_add:
            if not dry_run:
                # Add SDGs to the usecase
                usecase.sdgs.add(*sdgs_to_add)
                print(f"   ✅ Added {len(sdgs_to_add)} SDGs to usecase")

                # Optionally remove metadata
                if remove_metadata:
                    uc_meta.delete()  # type: ignore
                    print(f"   🗑️  Removed SDG metadata")

                migrated_count += 1
            else:
                print(f"   [DRY RUN] Would add {len(sdgs_to_add)} SDGs")
        else:
            error_count += 1
            print(f"   ⚠️  No valid SDGs found for this usecase")

    print(f"\n{'=' * 80}")
    if usecase_id:
        print(f"UseCase Migration Summary for UseCase ID {usecase_id}:")
    else:
        print(f"UseCase Migration Summary:")
    print(f"  Total usecases processed: {total_usecases}")
    print(f"  Successfully migrated: {migrated_count}")
    print(f"  Errors/Skipped: {error_count}")
    if not_found_sdgs:
        print(f"\n  SDGs not found in database:")
        for sdg_str in sorted(not_found_sdgs):
            print(f"    - {sdg_str}")
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


def list_available_sdgs() -> None:
    """List all available SDGs in the database."""
    print("\n" + "=" * 80)
    print("AVAILABLE SDGs IN DATABASE")
    print("=" * 80)

    sdgs = SDG.objects.all().order_by("code")

    if not sdgs.exists():
        print("\n⚠️  No SDGs found in database!")
        print("   Please populate SDGs first.")
        return

    print(f"\nTotal SDGs: {sdgs.count()}\n")
    for sdg in sdgs:
        print(f"  {sdg.code}: {sdg.name}")  # type: ignore
        if sdg.description:  # type: ignore
            print(f"     {sdg.description[:100]}...")  # type: ignore

    print("\n" + "=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate SDG metadata to sdgs field for usecases"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    parser.add_argument(
        "--remove-metadata",
        action="store_true",
        help="Remove SDG metadata after successful migration",
    )
    parser.add_argument(
        "--list-sdgs",
        action="store_true",
        help="List all available SDGs in the database",
    )
    parser.add_argument(
        "--update-index",
        action="store_true",
        help="Update search index after successful migration",
    )
    parser.add_argument(
        "--usecase-id",
        type=int,
        help="Migrate only the usecase with the specified ID",
    )

    args = parser.parse_args()

    if args.list_sdgs:
        list_available_sdgs()
        return

    print("\n" + "=" * 80)
    print("SDG METADATA MIGRATION SCRIPT")
    print("=" * 80)

    if args.dry_run:
        print("\n🔍 DRY RUN MODE - No changes will be made")

    if args.remove_metadata and not args.dry_run:
        print("\n⚠️  WARNING: SDG metadata will be DELETED after migration")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("Migration cancelled.")
            return

    # Run migration
    migrate_usecase_sdgs(
        dry_run=args.dry_run,
        remove_metadata=args.remove_metadata,
        usecase_id=args.usecase_id,
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
            update_search_index("usecases")

        print("\n📝 Next steps:")
        print("   1. Verify the migrated data in the admin panel")
        if not args.update_index:
            print(
                "   2. Re-index Elasticsearch: python manage.py search_index --rebuild"
            )
        print("   3. Test the SDG filters in the frontend")


if __name__ == "__main__":
    main()
