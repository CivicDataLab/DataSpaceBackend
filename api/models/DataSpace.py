from typing import Any

from django.db import models
from django.utils.text import slugify

from api.utils.file_paths import _dataspace_directory_path


class DataSpace(models.Model):
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=1000)
    logo = models.ImageField(upload_to=_dataspace_directory_path, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    homepage = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True, null=True)
    slug = models.SlugField(max_length=75, null=True, blank=False, unique=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        db_table = "dataspace"
