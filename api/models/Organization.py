from django.db import models

from api.enums import OrganizationTypes
from api.file_paths import _organization_directory_path


class Organization(models.Model):
    title = models.CharField(max_length=100)
    description = models.CharField(max_length=500)
    logo = models.ImageField(upload_to=_organization_directory_path, blank=True, null=True)
    issued = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    homepage = models.URLField(blank=True)
    contact_email = models.EmailField(blank=True, null=True)
    organization_types = models.CharField(
        max_length=50, choices=OrganizationTypes.choices
    )
    parent = models.ForeignKey("self", unique=False, blank=True, null=True, on_delete=models.SET_NULL,
                               related_name="parent_field", )
