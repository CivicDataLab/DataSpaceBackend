from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify

from api.utils.file_paths import _user_profile_image_directory_path
from authorization.consent import UserConsent


class Role(models.Model):
    """
    Role model for defining permissions in the system.
    """

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Define permissions for each role
    can_view = models.BooleanField(default=True)
    can_add = models.BooleanField(default=False)
    can_change = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name

    class Meta:
        db_table = "role"


class User(AbstractUser):
    """
    Custom User model that extends Django's AbstractUser.
    This model adds organization-related fields for Keycloak integration.
    """

    # Keycloak ID field to store the Keycloak user ID
    keycloak_id = models.CharField(max_length=255, unique=True, null=True, blank=True)

    # Organization relationship - a user can belong to multiple organizations
    organizations: models.ManyToManyField = models.ManyToManyField(
        "api.Organization", through="OrganizationMembership", related_name="members"
    )

    # Additional user profile fields
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(
        upload_to=_user_profile_image_directory_path, blank=True, null=True
    )
    github_profile = models.URLField(blank=True, null=True)
    linkedin_profile = models.URLField(blank=True, null=True)
    twitter_profile = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)

    @property
    def full_name(self) -> str:
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}"

    class Meta:
        db_table = "ds_user"


class OrganizationMembership(models.Model):
    """
    Intermediate model for User-Organization relationship.
    This model stores the role of a user within an organization.
    """

    user = models.ForeignKey("authorization.User", on_delete=models.CASCADE)
    organization = models.ForeignKey("api.Organization", on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_membership"
        unique_together = ("user", "organization")


class DatasetPermission(models.Model):
    """
    Model for dataset-specific permissions.
    This allows for more granular control beyond organization membership.
    """

    user = models.ForeignKey("authorization.User", on_delete=models.CASCADE)
    dataset = models.ForeignKey("api.Dataset", on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dataset_permission"
        unique_together = ("user", "dataset")
