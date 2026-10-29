from django.db import migrations

from api.utils.public_links import fill_missing_public_ids


def fill(apps, schema_editor):
    fill_missing_public_ids(apps.get_model("api", "Event"))


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0056_event_public_id"),
    ]

    operations = [
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
