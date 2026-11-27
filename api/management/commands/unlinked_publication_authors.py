"""List publications whose saved author names are not linked to any user.

    python manage.py unlinked_publication_authors

Read-only. Run on a server before ``Publication.authors`` is removed: each line
is a publication that would lose those names. Uses the same matching as
migration 0068. Prints names, so run it in a terminal, never in a CI step.
"""

from typing import Any

from django.core.management.base import BaseCommand

from api.models import Publication
from api.utils.publication_contributors import index_members, index_users, split_authors
from authorization.models import OrganizationMembership, User


class Command(BaseCommand):
    help = "List publications with author names that match no contributor user."

    def handle(self, *args: Any, **options: Any) -> None:
        index = index_users(User.objects.values_list("id", "first_name", "last_name", "username"))
        members = index_members(
            OrganizationMembership.objects.values_list("user_id", "organization_id")
        )

        found = 0
        publications = (
            Publication.objects.exclude(authors=[])
            .select_related("organization", "user")
            .order_by("created")
        )
        for publication in publications.iterator():
            names = [name for name in (publication.authors or []) if isinstance(name, str)]
            _, unlinked = split_authors(
                names,
                index,
                publication.user_id,
                members.get(publication.organization_id or 0, set()),
            )
            if not unlinked:
                continue
            found += 1
            owner = (
                publication.organization.name
                if publication.organization
                else getattr(publication.user, "username", "-")
            )
            self.stdout.write(
                f"{publication.id}  {publication.status}  {publication.title!r}  "
                f"owner={owner!r}  unlinked={unlinked}"
            )
        self.stdout.write(f"{found} publication(s) with unlinked author names")
