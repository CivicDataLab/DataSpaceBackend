from django.db import migrations, models

MODELS = ["aimodel", "collaborative", "dataset", "publication", "usecase"]


class Migration(migrations.Migration):
    """Add public_id (nullable for now) to every public module.

    Also drops the unique rule on dataset, publication and use case slugs and
    on use case / collaborative titles: links use public_id, so titles may
    repeat. Collaborative slugs stay unique (the slug is also the subdomain).
    Filled for existing rows in 0061, made unique and required in 0062.
    """

    dependencies = [
        ("api", "0059_event_search_cover_url"),
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
