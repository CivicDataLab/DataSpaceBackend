from typing import Any

from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from api.utils.file_paths import _catalog_directory_path


class Catalog(models.Model):
    name = models.CharField(max_length=255)
    datasets = models.ManyToManyField("api.Dataset", related_name="catalogs")
    logo = models.ImageField(upload_to=_catalog_directory_path, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    homepage = models.URLField(blank=True)
    slug = models.SlugField(max_length=75, null=True, blank=False, unique=True)

    class Meta:
        verbose_name = _("catalog")
        verbose_name_plural = _("catalogs")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("catalog_detail", kwargs={"pk": self.pk})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.slug = slugify(self.name)
        super().save(*args, **kwargs)
