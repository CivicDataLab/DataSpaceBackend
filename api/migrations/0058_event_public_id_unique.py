from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0057_fill_event_public_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="public_id",
            field=models.CharField(editable=False, max_length=12, unique=True),
        ),
    ]
