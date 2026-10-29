import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0054_add_source_identifier_metadata"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Event",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(blank=True, max_length=300)),
                ("public_id", models.CharField(editable=False, max_length=12, unique=True)),
                ("location", models.CharField(blank=True, max_length=300)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("luma_embed", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published")],
                        default="DRAFT",
                        max_length=50,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="events",
                        to="api.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Event",
                "verbose_name_plural": "Events",
                "db_table": "event",
                "ordering": ["-modified"],
                "indexes": [
                    models.Index(
                        fields=["organization", "-modified"], name="event_org_modified_idx"
                    ),
                    models.Index(fields=["user", "-modified"], name="event_user_modified_idx"),
                    models.Index(fields=["status"], name="event_status_idx"),
                ],
            },
        ),
    ]
