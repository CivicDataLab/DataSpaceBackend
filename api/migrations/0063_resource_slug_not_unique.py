from django.db import migrations, models


class Migration(migrations.Migration):
    """Resource slugs no longer need to be unique (#229).

    Nothing looks a resource up by slug, and the unique rule made two uploads
    of the same file name at the same moment fail.
    """

    dependencies = [
        ("api", "0062_public_ids_unique"),
    ]

    operations = [
        migrations.AlterField(
            model_name="resource",
            name="slug",
            field=models.SlugField(max_length=255),
        ),
    ]
