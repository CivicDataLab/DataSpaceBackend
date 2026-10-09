"""Seed the starting Resource Types on every environment.

Publishing a publication requires an active Resource Type, but the types were
only created by `manage.py seed_resource_types`, which deploys never run, so
dev and prod had none and nothing could be published.

Same behaviour as the command: create the starting types that are missing and
switch any deactivated one back on. Types an admin added are not touched. The
list is copied here on purpose, so later edits to the command cannot change
what this migration does. Reversing it deletes nothing, since publications may
already point at these types.
"""

from django.db import migrations
from django.utils.text import slugify

STARTING_RESOURCE_TYPES = [
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


def seed_resource_types(apps, schema_editor):
    # Historical models skip ResourceType.save(), which is where the slug is
    # normally set, so the slug is given explicitly here.
    ResourceType = apps.get_model("api", "ResourceType")
    for name in STARTING_RESOURCE_TYPES:
        resource_type, created = ResourceType.objects.get_or_create(
            name=name, defaults={"is_active": True, "slug": slugify(name)}
        )
        if not created and not resource_type.is_active:
            resource_type.is_active = True
            resource_type.save(update_fields=["is_active"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0050_resourcefiledetails_sha256"),
    ]

    operations = [
        migrations.RunPython(seed_resource_types, migrations.RunPython.noop),
    ]
