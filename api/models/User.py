from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom User model that extends Django's AbstractUser.
    This model adds organization-related fields for Keycloak integration.
    """

    # Keycloak ID field to store the Keycloak user ID
    keycloak_id = models.CharField(max_length=255, unique=True, null=True, blank=True)

    # Organization relationship - a user can belong to multiple organizations
    organizations: models.ManyToManyField = models.ManyToManyField(
        "api.Organization", through="UserOrganization", related_name="members"
    )

    # Additional user profile fields can be added here
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(
        upload_to="profile_pictures/", blank=True, null=True
    )

    class Meta:
        db_table = "user"


class UserOrganization(models.Model):
    """
    Intermediate model for User-Organization relationship.
    This model stores the role of a user within an organization.
    """

    USER_ROLES = [
        ("admin", "Administrator"),
        ("editor", "Editor"),
        ("viewer", "Viewer"),
    ]

    user = models.ForeignKey("api.User", on_delete=models.CASCADE)
    organization = models.ForeignKey("api.Organization", on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=USER_ROLES, default="viewer")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_organization"
        unique_together = ("user", "organization")
