"""
Django management command to seed the initial Resource Type lookup values.

Idempotent — re-running only creates the types that are missing and never
duplicates a name. The starting set is left active, so a deactivated starting
type is switched back on; types an admin adds beyond this list are left as
they are. Admins manage the list afterwards (add / rename / deactivate extra
types) from the Django admin, no deploy required.

Usage:
    python manage.py seed_resource_types
"""

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import ResourceType

# The starting set of Resource Types. Admin-editable after seeding.
INITIAL_RESOURCE_TYPES = [
    "Report",
    "Article",
    "Policy Brief",
    "Research Paper",
    "Case Study",
    "Guide",
    "Toolkit",
    "Presentation",
    "Fact Sheet",
    "Working Paper",
]


class Command(BaseCommand):
    help = "Seed the initial Resource Type lookup values (idempotent)"

    def handle(self, *args: Any, **options: Any) -> None:
        created_count = 0
        with transaction.atomic():
            for name in INITIAL_RESOURCE_TYPES:
                resource_type, created = ResourceType.objects.get_or_create(
                    name=name, defaults={"is_active": True}
                )
                if created:
                    created_count += 1
                elif not resource_type.is_active:
                    resource_type.is_active = True
                    resource_type.save(update_fields=["is_active"])

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Resource Types seeded ({created_count} created, "
                f"{len(INITIAL_RESOURCE_TYPES) - created_count} already present)"
            )
        )
