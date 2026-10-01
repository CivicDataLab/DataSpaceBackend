"""Management command to merge external contributors into registered users."""

from django.core.management.base import BaseCommand

from api.models import ExternalContributor
from api.services.external_contributor_service import merge_external_contributor_into_user


class Command(BaseCommand):
    help = "Merge external contributors into registered users by email."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be merged without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        external_contributors = ExternalContributor.objects.all().order_by("id")
        merged_count = 0
        no_match_count = 0

        for external_contributor in external_contributors:
            if not external_contributor.email:
                self.stdout.write(
                    self.style.WARNING(
                        f"External contributor {external_contributor.id} ({external_contributor.name}) has no email, skipping"
                    )
                )
                continue

            # Check if there's a user with this email
            from authorization.models import User

            user = User.objects.filter(email__iexact=external_contributor.email.strip()).first()

            if not user:
                no_match_count += 1
                self.stdout.write(
                    f"No user found for external contributor {external_contributor.id} ({external_contributor.email})"
                )
                continue

            if dry_run:
                usecases_count = external_contributor.usecases.count()
                collabs_count = external_contributor.collaboratives.count()
                pubs_count = external_contributor.publications.count()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[DRY RUN] Would merge external contributor {external_contributor.id} ({external_contributor.name}) "
                        f"into user {user.id} ({user.username}): "
                        f"{usecases_count} use-cases, {collabs_count} collaboratives, {pubs_count} publications"
                    )
                )
                merged_count += 1
            else:
                if merge_external_contributor_into_user(user):
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Merged external contributor {external_contributor.id} ({external_contributor.name}) "
                            f"into user {user.id} ({user.username})"
                        )
                    )
                    merged_count += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to merge external contributor {external_contributor.id} ({external_contributor.name})"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nMerge complete: {merged_count} merged, {no_match_count} with no matching user"
            )
        )
