from typing import Any

from django.db import models
from django.utils.text import slugify

from api.utils.enums import OrganizationTypes
from api.utils.file_paths import _organization_directory_path


class Organization(models.Model):
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=1000)
    logo = models.ImageField(
        upload_to=_organization_directory_path, blank=True, null=True, max_length=300
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    homepage = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True, null=True)
    organization_types = models.CharField(
        max_length=100, choices=OrganizationTypes.choices
    )
    parent = models.ForeignKey(
        "api.Organization",
        unique=False,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="parent_field",
    )
    slug = models.SlugField(max_length=75, null=True, blank=False, unique=True)
    github_profile = models.URLField(blank=True, null=True)
    linkedin_profile = models.URLField(blank=True, null=True)
    twitter_profile = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "organization"
