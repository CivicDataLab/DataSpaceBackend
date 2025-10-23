from django.contrib import admin

from api.models import (
    AIModel,
    Catalog,
    Dataset,
    ModelAPIKey,
    ModelEndpoint,
    Organization,
    UseCase,
)


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


@admin.register(UseCase)
class UseCaseAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "created")
    search_fields = ("title", "slug")
    list_filter = ("organization",)


@admin.register(Catalog)
class CatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created")


class ModelEndpointInline(admin.TabularInline):
    model = ModelEndpoint
    extra = 1
    fields = ("url", "http_method", "auth_type", "is_primary", "is_active")


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "name",
        "provider",
        "model_type",
        "status",
        "is_public",
        "is_active",
        "created_at",
    )
    list_filter = (
        "provider",
        "model_type",
        "status",
        "is_public",
        "is_active",
        "organization",
    )
    search_fields = ("name", "display_name", "description", "provider_model_id")
    readonly_fields = ("created_at", "updated_at", "last_tested_at")
    inlines = [ModelEndpointInline]
    fieldsets = (
        (
            "Basic Information",
            {"fields": ("name", "display_name", "version", "description")},
        ),
        (
            "Model Configuration",
            {"fields": ("model_type", "provider", "provider_model_id")},
        ),
        ("Ownership", {"fields": ("organization", "user")}),
        (
            "Capabilities",
            {"fields": ("supports_streaming", "max_tokens", "supported_languages")},
        ),
        (
            "Schema",
            {"fields": ("input_schema", "output_schema"), "classes": ("collapse",)},
        ),
        ("Metadata", {"fields": ("tags", "metadata"), "classes": ("collapse",)}),
        ("Status & Visibility", {"fields": ("status", "is_public", "is_active")}),
        (
            "Performance Metrics",
            {
                "fields": (
                    "average_latency_ms",
                    "success_rate",
                    "last_audit_score",
                    "audit_count",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at", "last_tested_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(ModelEndpoint)
class ModelEndpointAdmin(admin.ModelAdmin):
    list_display = (
        "model",
        "url",
        "http_method",
        "auth_type",
        "is_primary",
        "is_active",
        "success_rate",
    )
    list_filter = ("http_method", "auth_type", "is_primary", "is_active")
    search_fields = ("url", "model__name", "model__display_name")
    readonly_fields = (
        "created_at",
        "updated_at",
        "last_success_at",
        "last_failure_at",
        "success_rate",
    )
    fieldsets = (
        ("Model", {"fields": ("model",)}),
        ("Endpoint Configuration", {"fields": ("url", "http_method")}),
        ("Authentication", {"fields": ("auth_type", "auth_header_name")}),
        (
            "Request Configuration",
            {
                "fields": ("headers", "request_template", "response_path"),
                "classes": ("collapse",),
            },
        ),
        (
            "Settings",
            {
                "fields": (
                    "timeout_seconds",
                    "max_retries",
                    "is_primary",
                    "is_active",
                    "rate_limit_per_minute",
                )
            },
        ),
        (
            "Monitoring",
            {
                "fields": (
                    "last_success_at",
                    "last_failure_at",
                    "total_requests",
                    "failed_requests",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(ModelAPIKey)
class ModelAPIKeyAdmin(admin.ModelAdmin):
    list_display = (
        "model",
        "name",
        "key_type",
        "is_active",
        "expires_at",
        "usage_count",
    )
    list_filter = ("key_type", "is_active")
    search_fields = ("name", "model__name", "model__display_name")
    readonly_fields = ("created_at", "updated_at", "last_used_at", "usage_count")
    exclude = ("encrypted_key",)  # Don't show encrypted key in admin
    fieldsets = (
        ("Model", {"fields": ("model",)}),
        (
            "Key Information",
            {"fields": ("name", "key_type", "is_active", "expires_at")},
        ),
        (
            "Usage Tracking",
            {"fields": ("last_used_at", "usage_count"), "classes": ("collapse",)},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
