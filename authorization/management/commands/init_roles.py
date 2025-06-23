from typing import Any

from django.core.management.base import BaseCommand

from authorization.models import Role


class Command(BaseCommand):
    help = "Initialize default roles in the system"

    def handle(self, *args: Any, **options: Any) -> None:
        # Define the default roles
        default_roles = [
            {
                "name": "admin",
                "description": "Administrator with full access",
                "can_view": True,
                "can_add": True,
                "can_change": True,
                "can_delete": True,
            },
            {
                "name": "editor",
                "description": "Editor with ability to view, add, and change content",
                "can_view": True,
                "can_add": True,
                "can_change": True,
                "can_delete": False,
            },
            {
                "name": "viewer",
                "description": "Viewer with read-only access",
                "can_view": True,
                "can_add": False,
                "can_change": False,
                "can_delete": False,
            },
            {
                "name": "owner",
                "description": "Owner with full access",
                "can_view": True,
                "can_add": True,
                "can_change": True,
                "can_delete": True,
            },
        ]

        # Create or update the roles
        for role_data in default_roles:
            role, created = Role.objects.update_or_create(
                name=role_data["name"],
                defaults={
                    "description": role_data["description"],
                    "can_view": role_data["can_view"],
                    "can_add": role_data["can_add"],
                    "can_change": role_data["can_change"],
                    "can_delete": role_data["can_delete"],
                },
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created role: {role.name}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Updated role: {role.name}"))

        self.stdout.write(self.style.SUCCESS("Successfully initialized roles"))
