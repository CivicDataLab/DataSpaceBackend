from django.contrib import admin

from api.models import (
    AIModel,
    AIModelVersion,
    Catalog,
    Collaborative,
    CollaborativeMetadata,
    CollaborativeOrganizationRelationship,
    Dataset,
    DatasetMetadata,
    DataSpace,
    Geography,
    Metadata,
    ModelAPIKey,
    ModelEndpoint,
    Organization,
    PromptDataset,
    PromptResource,
    Resource,
    ResourceChartDetails,
    ResourceChartImage,
    ResourceDataTable,
    ResourceFileDetails,
    ResourceMetadata,
    ResourcePreviewDetails,
    ResourceSchema,
    ResourceVersion,
    SDG,
    Sector,
    Tag,
    UseCase,
    UseCaseDashboard,
    UseCaseMetadata,
    UseCaseOrganizationRelationship,
    VersionProvider,
)


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


# ---------------------------------------------------------------------------
# Dataset & related
# ---------------------------------------------------------------------------

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("value",)
    search_fields = ("value",)


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "created")
    list_filter = ("organization",)
    search_fields = ("title", "description")


@admin.register(DatasetMetadata)
class DatasetMetadataAdmin(admin.ModelAdmin):
    list_display = ("dataset", "metadata_item", "value")
    list_filter = ("dataset",)
    search_fields = ("value",)


@admin.register(PromptDataset)
class PromptDatasetAdmin(admin.ModelAdmin):
    list_display = ("title", "task_type", "domain", "purpose", "organization", "created")
    list_filter = ("task_type", "domain", "purpose", "organization")
    search_fields = ("title", "description")


# ---------------------------------------------------------------------------
# UseCase & related
# ---------------------------------------------------------------------------

@admin.register(UseCase)
class UseCaseAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "created")
    search_fields = ("title", "slug")
    list_filter = ("organization",)


@admin.register(UseCaseDashboard)
class UseCaseDashboardAdmin(admin.ModelAdmin):
    list_display = ("usecase", "name")
    search_fields = ("usecase__title", "name")


@admin.register(UseCaseMetadata)
class UseCaseMetadataAdmin(admin.ModelAdmin):
    list_display = ("usecase", "metadata_item", "value")
    list_filter = ("usecase",)
    search_fields = ("value",)


@admin.register(UseCaseOrganizationRelationship)
class UseCaseOrganizationRelationshipAdmin(admin.ModelAdmin):
    list_display = ("usecase", "organization", "relationship_type")
    list_filter = ("relationship_type",)
    search_fields = ("usecase__title", "organization__name")


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@admin.register(Catalog)
class CatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created")


# ---------------------------------------------------------------------------
# Collaborative & related
# ---------------------------------------------------------------------------

@admin.register(Collaborative)
class CollaborativeAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "created")
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(CollaborativeMetadata)
class CollaborativeMetadataAdmin(admin.ModelAdmin):
    list_display = ("collaborative", "metadata_item", "value")
    list_filter = ("collaborative",)
    search_fields = ("value",)


@admin.register(CollaborativeOrganizationRelationship)
class CollaborativeOrganizationRelationshipAdmin(admin.ModelAdmin):
    list_display = ("collaborative", "organization", "relationship_type")
    list_filter = ("relationship_type",)
    search_fields = ("collaborative__title", "organization__name")


# ---------------------------------------------------------------------------
# Resource & related
# ---------------------------------------------------------------------------

class ResourceFileDetailsInline(admin.StackedInline):
    model = ResourceFileDetails
    extra = 0


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("name", "dataset", "type", "created")
    list_filter = ("type", "dataset")
    search_fields = ("name", "description")
    inlines = [ResourceFileDetailsInline]


@admin.register(ResourceFileDetails)
class ResourceFileDetailsAdmin(admin.ModelAdmin):
    list_display = ("resource",)
    search_fields = ("resource__title",)


@admin.register(ResourcePreviewDetails)
class ResourcePreviewDetailsAdmin(admin.ModelAdmin):
    list_display = ("resource",)
    search_fields = ("resource__title",)


@admin.register(ResourceDataTable)
class ResourceDataTableAdmin(admin.ModelAdmin):
    list_display = ("resource",)
    search_fields = ("resource__title",)


@admin.register(ResourceVersion)
class ResourceVersionAdmin(admin.ModelAdmin):
    list_display = ("resource", "version_number", "created_at")
    list_filter = ("resource",)
    search_fields = ("resource__name", "version_number")


@admin.register(ResourceChartDetails)
class ResourceChartDetailsAdmin(admin.ModelAdmin):
    list_display = ("resource",)
    search_fields = ("resource__title",)


@admin.register(ResourceChartImage)
class ResourceChartImageAdmin(admin.ModelAdmin):
    list_display = ("name", "dataset", "status")
    list_filter = ("dataset", "status")
    search_fields = ("name", "description")


@admin.register(ResourceMetadata)
class ResourceMetadataAdmin(admin.ModelAdmin):
    list_display = ("resource", "metadata_item", "value")
    list_filter = ("resource",)
    search_fields = ("value",)


@admin.register(ResourceSchema)
class ResourceSchemaAdmin(admin.ModelAdmin):
    list_display = ("resource",)
    search_fields = ("resource__title",)


@admin.register(PromptResource)
class PromptResourceAdmin(admin.ModelAdmin):
    list_display = ("resource", "prompt_format", "created")
    list_filter = ("resource__dataset", "prompt_format")
    search_fields = ("resource__name",)


# ---------------------------------------------------------------------------
# AIModel & related
# ---------------------------------------------------------------------------

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
        "domain",
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
        ("Metadata", {"fields": ("tags", "domain", "metadata"), "classes": ("collapse",)}),
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


@admin.register(AIModelVersion)
class AIModelVersionAdmin(admin.ModelAdmin):
    list_display = ("ai_model", "version", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("ai_model__name", "version")
    readonly_fields = ("created_at", "updated_at")


@admin.register(VersionProvider)
class VersionProviderAdmin(admin.ModelAdmin):
    list_display = ("version", "provider", "is_primary", "is_active")
    list_filter = ("provider", "is_primary", "is_active")
    search_fields = ("version__ai_model__name", "provider_model_id")


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



# ---------------------------------------------------------------------------
# Geography / SDG / Sector
# ---------------------------------------------------------------------------

@admin.register(Geography)
class GeographyAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(SDG)
class SDGAdmin(admin.ModelAdmin):
    list_display = ("name", "number")
    search_fields = ("name",)


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


# ---------------------------------------------------------------------------
# DataSpace
# ---------------------------------------------------------------------------

@admin.register(DataSpace)
class DataSpaceAdmin(admin.ModelAdmin):
    list_display = ("name", "created")
    search_fields = ("name",)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

@admin.register(Metadata)
class MetadataAdmin(admin.ModelAdmin):
    list_display = ("label", "data_type", "type", "model", "enabled", "filterable", "created")
    list_filter = ("data_type", "type", "model", "enabled", "filterable")
    search_fields = ("label", "urn")
