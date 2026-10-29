from django.db import migrations, models


class Migration(migrations.Migration):
    """Add Event.public_id (nullable for now) and drop the unique rule on slug.

    Filled for existing rows in 0057, made unique and required in 0058.
    """

    dependencies = [
        ("api", "0055_event"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="public_id",
            field=models.CharField(editable=False, max_length=12, null=True),
        ),
        migrations.AlterField(
            model_name="event",
            name="slug",
            field=models.SlugField(max_length=255),
        ),
    ]
