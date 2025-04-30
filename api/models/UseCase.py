from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from django.db import models
from django.utils.text import slugify

if TYPE_CHECKING:
    from api.models.Dataset import Dataset

from api.utils.enums import UseCaseRunningStatus, UseCaseStatus
from api.utils.file_paths import _use_case_directory_path


class UseCase(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200, unique=True, blank=True, null=True)
    summary = models.CharField(max_length=10000, blank=True, null=True)
    logo = models.ImageField(upload_to=_use_case_directory_path, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    website = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True, null=True)
    slug = models.SlugField(max_length=75, null=True, blank=True, unique=True)
    status = models.CharField(
        max_length=50, default=UseCaseStatus.DRAFT, choices=UseCaseStatus.choices
    )
    datasets = models.ManyToManyField("api.Dataset", blank=True)
    tags = models.ManyToManyField("api.Tag", blank=True)
    running_status = models.CharField(
        max_length=50,
        default=UseCaseRunningStatus.INITIATED,
        choices=UseCaseRunningStatus.choices,
    )
    sectors = models.ManyToManyField("api.Sector", blank=True, related_name="usecases")
    started_on = models.DateField(blank=True, null=True)
    completed_on = models.DateField(blank=True, null=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.title and not self.slug:
            self.slug = slugify(cast(str, self.title))
        super().save(*args, **kwargs)

    class Meta:
        db_table = "use_case"
