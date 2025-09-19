from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from authorization.models import DatasetPermission, OrganizationMembership, Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "can_view",
        "can_add",
        "can_change",
        "can_delete",
        "created_at",
    )
    search_fields = ("name",)
    list_filter = ("can_view", "can_add", "can_change", "can_delete")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_superuser",
    )
    # Make a copy of the original fieldsets to avoid modifying the original
    fieldsets = list(BaseUserAdmin.fieldsets) + [  # type: ignore
        (
            "Keycloak Information",
            {
                "fields": [
                    "keycloak_id",
                ]
            },
        ),
        (
            "Profile Information",
            {
                "fields": [
                    "bio",
                    "profile_picture",
                    "github_profile",
                    "linkedin_profile",
                    "twitter_profile",
                    "location",
                ]
            },
        ),
    ]  # type: ignore
    search_fields = ("username", "email", "first_name", "last_name", "keycloak_id")


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "created_at")
    list_filter = ("role", "organization")
    search_fields = ("user__username", "user__email", "organization__name")
    autocomplete_fields = ("user", "organization", "role")


@admin.register(DatasetPermission)
class DatasetPermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "dataset", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email", "dataset__title")
    autocomplete_fields = ("user", "dataset", "role")
