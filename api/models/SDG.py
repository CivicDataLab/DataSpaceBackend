import uuid
from typing import Any

from django.db import models
from django.utils.text import slugify


class SDG(models.Model):
    """Model for Sustainable Development Goals (SDGs)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, null=False, blank=False)
    code = models.CharField(
        max_length=10, unique=True, null=False, blank=False
    )  # e.g., "SDG1", "SDG2"
    number = models.IntegerField(
        null=True, blank=True
    )  # Numeric value for proper ordering (1, 2, 3... 17)
    description = models.TextField(null=True, blank=True)
    slug = models.SlugField(max_length=100, null=True, blank=False, unique=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    class Meta:
        db_table = "sdg"
        verbose_name = "SDG"
        verbose_name_plural = "SDGs"
        ordering = ["number"]
