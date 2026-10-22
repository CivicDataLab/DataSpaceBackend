"""Add the "Source identifier" dataset metadata item.

CivicDataLab's scrapers (DataSpace-Scrapers) fill it on every dataset they upload with
dataspace-scrapers/<scraper_id>/<dataset_key>, and read it back to recognise their own
datasets, so a dataset is never created twice and their upload records can be rebuilt
from DataSpace. People never fill it in. Platform imports (Kaggle, Hugging Face, GitHub)
also fill it, with the platform's own ID, because the label matches the import's
"source identifier" field; only values starting with dataspace-scrapers/ are a scraper's.

Creates the item if it is missing and switches it back on if an admin switched it off.
Reversing it deletes nothing, since datasets may already carry values for it.
"""

from django.db import migrations

LABEL = "Source identifier"


def add_source_identifier(apps, schema_editor):
    Metadata = apps.get_model("api", "Metadata")
    item, created = Metadata.objects.get_or_create(
        label=LABEL,
        model="DATASET",
        defaults={
            "urn": "dataspace-scrapers:source-identifier",
            "data_type": "STRING",
            "type": "OPTIONAL",
            "data_standard": "NA",
            "options": None,
            "validator": [],
            "enabled": True,
            "filterable": False,
        },
    )
    if not created and not item.enabled:
        item.enabled = True
        item.save(update_fields=["enabled"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0053_alter_collaborative_summary"),
    ]

    operations = [
        migrations.RunPython(add_source_identifier, migrations.RunPython.noop),
    ]
