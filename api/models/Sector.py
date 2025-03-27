import uuid
from typing import Any, Dict, List, Optional

from django.db import models
from django.utils.text import slugify


class Sector(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=75, unique=True, null=False, blank=False)
    description = models.CharField(max_length=1000, null=True, blank=True)
    parent_id = models.ForeignKey(
        "api.Sector", on_delete=models.CASCADE, null=True, blank=True
    )
    slug = models.SlugField(max_length=75, null=True, blank=False, unique=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        db_table = "sector"
        verbose_name_plural = "sectors"
