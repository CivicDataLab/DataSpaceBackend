import logging
from typing import Any, List, Optional, cast

from django.core.management.base import BaseCommand, CommandParser

from authorization.models import User

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Promotes a user to superuser status by username or email"  # type: ignore[assignment]

    def add_arguments(self, parser: CommandParser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "identifier",
            type=str,
            help="Username or email of the user to promote",
        )

    def handle(self, *args: Any, **options: Any) -> None:  # type: ignore[no-untyped-def]
        identifier = options["identifier"]

        # Try to find the user by username or email
        user = None
        try:
            user = User.objects.filter(username=identifier).first()
            if not user:
                user = User.objects.filter(email=identifier).first()

            if not user:
                self.stdout.write(
                    self.style.ERROR(
                        f"User with username or email '{identifier}' not found"
                    )
                )
                return

            # Promote the user to superuser
            user.is_staff = True
            user.is_superuser = True
            user.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully promoted {user.username} (ID: {user.id}) to superuser status"
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error promoting user: {str(e)}"))
