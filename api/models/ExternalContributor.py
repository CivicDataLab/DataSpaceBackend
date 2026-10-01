from typing import Any

from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower

from api.utils.file_paths import _external_contributor_directory_path


class ExternalContributor(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    image = models.ImageField(
        upload_to=_external_contributor_directory_path,
        max_length=300,
        blank=True,
        null=True,
    )
    organization = models.CharField(max_length=255, blank=True, null=True)
    designation = models.CharField(max_length=200, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    has_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = self.email.lower().strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name

    class Meta:
        db_table = "external_contributor"
        ordering = ["name"]
        constraints = [
            UniqueConstraint(
                Lower("email"), name="unique_external_contributor_email_lower"
            ),
        ]
