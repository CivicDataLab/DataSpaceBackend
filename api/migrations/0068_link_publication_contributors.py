"""Link existing publications to the users their saved author names stand for.

The wizard picked real users but saved only display names in ``authors``. Each
name that matches exactly one user (owner, then a single organisation member,
breaks a tie) is added to ``contributors``. ``authors`` is left untouched: a
failed deploy rolls back the image but not migrations, and the old code still
reads it. Unmatched names stay unlinked; ``manage.py unlinked_publication_authors``
lists them on the server. Only counts are printed: deploy logs are public.
"""

from typing import Any

from django.db import migrations

from api.utils.publication_contributors import index_members, index_users, split_authors


def link_contributors(apps: Any, schema_editor: Any) -> None:
    Publication = apps.get_model("api", "Publication")
    User = apps.get_model("authorization", "User")
    OrganizationMembership = apps.get_model("authorization", "OrganizationMembership")

    publications = list(Publication.objects.exclude(authors=[]))
    if not publications:
        return

    index = index_users(User.objects.values_list("id", "first_name", "last_name", "username"))
    members = index_members(
        OrganizationMembership.objects.values_list("user_id", "organization_id")
    )

    linked_count = unlinked_count = 0
    for publication in publications:
        names = [name for name in (publication.authors or []) if isinstance(name, str)]
        linked, unlinked = split_authors(
            names,
            index,
            publication.user_id,
            members.get(publication.organization_id, set()),
        )
        if linked:
            publication.contributors.add(*linked)
        linked_count += len(linked)
        unlinked_count += len(unlinked)

    print(
        f"\n  publication contributors: {linked_count} linked, "
        f"{unlinked_count} names not linked"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0067_publication_contributors"),
        ("authorization", "0005_profile_picture_storage"),
    ]

    operations = [
        # Nothing to undo here: reversing 0067 drops the whole link table.
        migrations.RunPython(link_contributors, migrations.RunPython.noop),
    ]
