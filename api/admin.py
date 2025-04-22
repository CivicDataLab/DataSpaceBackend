from django.contrib import admin

from api.models import Dataset, Organization


# Register models needed for authorization app's autocomplete fields
@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "created")
    list_filter = ("organization",)
    search_fields = ("title", "description")
