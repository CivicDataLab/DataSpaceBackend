from typing import Any, Optional

from django.db import models
from django.utils.text import slugify

from api.utils.enums import OrganizationTypes
from api.utils.file_paths import _organization_directory_path
from api.utils.storage import public_storage

SLUG_MAX_LENGTH = 75
NAME_TAKEN = "An organization with this or a very similar name already exists."
NAME_WITHOUT_LETTERS = "Organization name must contain letters or numbers."


def organization_slug(name: str) -> str:
    """The slug saved for a name; the organization header and dashboard links use it."""
    return slugify(name)[:SLUG_MAX_LENGTH].strip("-")


def organization_name_error(name: str, organization_id: Optional[int] = None) -> Optional[str]:
    """Why `name` cannot be saved for this organization, or None.

    The slug is made from the name on every save and must be unique, so two names
    with the same slug ("CivicDataLab", "civicdatalab!") cannot both exist. An
    empty slug (a name of symbols, or only non-Latin letters) cannot work as a
    link either.
    """
    slug = organization_slug(name or "")
    if not slug:
        return NAME_WITHOUT_LETTERS
    others = Organization.objects.filter(slug=slug)
    if organization_id is not None:
        others = others.exclude(pk=organization_id)
    return NAME_TAKEN if others.exists() else None


class Organization(models.Model):
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=1000)
    logo = models.ImageField(
        upload_to=_organization_directory_path,
        storage=public_storage,
        blank=True,
        null=True,
        max_length=300,
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    homepage = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True, null=True)
    organization_types = models.CharField(max_length=100, choices=OrganizationTypes.choices)
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
        self.slug = organization_slug(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "organization"
