from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0048_platform_import"),
    ]

    operations = [
        migrations.AddField(
            model_name="resourcefiledetails",
            name="sha256",
            field=models.CharField(
                blank=True,
                help_text="SHA-256 of the file contents, computed when the file is saved.",
                max_length=64,
                null=True,
            ),
        ),
    ]
