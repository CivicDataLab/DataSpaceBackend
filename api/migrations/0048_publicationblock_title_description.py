from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0047_resourcetype_publication_collaborative_publications_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="publicationblock",
            name="title",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="publicationblock",
            name="description",
            field=models.TextField(blank=True, null=True),
        ),
    ]
