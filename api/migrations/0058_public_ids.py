import django.core.validators
from django.db import migrations, models

MODELS = ["aimodel", "collaborative", "dataset", "publication", "usecase"]


class Migration(migrations.Migration):
    """Add public_id (nullable for now) to every public module.

    Also drops the unique rule on slugs and on use case / collaborative titles:
    links use public_id, so titles may repeat. Filled for existing rows in
    0057, made unique and required in 0058.
    """

    dependencies = [
        ("api", "0057_repair_event_search_index"),
    ]

    operations = [
        *[
            migrations.AddField(
                model_name=model,
                name="public_id",
                field=models.CharField(editable=False, max_length=12, null=True),
            )
            for model in MODELS
        ],
        migrations.AlterField(
            model_name="collaborative",
            name="slug",
            field=models.SlugField(
                blank=True,
                max_length=75,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message=(
                            "Slug must be lowercase and contain only alphanumeric "
                            "characters and hyphens."
                        ),
                        regex="^[a-z0-9]+(?:-[a-z0-9]+)*$",
                    )
                ],
            ),
        ),
        migrations.AlterField(
            model_name="collaborative",
            name="title",
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name="dataset",
            name="slug",
            field=models.SlugField(max_length=255),
        ),
        migrations.AlterField(
            model_name="publication",
            name="slug",
            field=models.SlugField(max_length=255),
        ),
        migrations.AlterField(
            model_name="usecase",
            name="slug",
            field=models.SlugField(blank=True, max_length=75, null=True),
        ),
        migrations.AlterField(
            model_name="usecase",
            name="title",
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
    ]
