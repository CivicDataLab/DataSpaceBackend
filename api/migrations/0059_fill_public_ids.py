from django.db import migrations

from api.utils.public_links import fill_missing_public_ids

MODELS = ["AIModel", "Collaborative", "Dataset", "Publication", "UseCase"]


def fill(apps, schema_editor):
    for name in MODELS:
        fill_missing_public_ids(apps.get_model("api", name))


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0058_public_ids"),
    ]

    operations = [
        migrations.RunPython(fill, migrations.RunPython.noop),
    ]
