import uuid
from typing import Any

from django.db import models
from django.utils.text import slugify


class ResourceType(models.Model):
    """Admin-managed lookup for a Resource's type (Report, Article, Policy Brief, ...).

    A flat, non-hierarchical list — no parent self-FK. Admins can add, rename,
    or deactivate a type without a code release. Deactivating (``is_active=False``)
    keeps historical references intact while hiding the type from new selections.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=75, unique=True, null=False, blank=False)
    description = models.CharField(max_length=1000, null=True, blank=True)
    slug = models.SlugField(max_length=75, null=True, blank=False, unique=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        db_table = "resource_type"
        verbose_name = "Resource Type"
        verbose_name_plural = "Resource Types"
        ordering = ["name"]
