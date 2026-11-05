from django.db import migrations, models

MODELS = ["aimodel", "collaborative", "dataset", "publication", "usecase"]


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0061_fill_public_ids"),
    ]

    operations = [
        migrations.AlterField(
            model_name=model,
            name="public_id",
            field=models.CharField(editable=False, max_length=12, unique=True),
        )
        for model in MODELS
    ]
