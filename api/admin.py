from collections import Counter

from django.contrib import admin, messages
from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection, IntegrityError
from django.db.models import F, Q


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
    ProcessedFile,
    PromptResource,
    Resource,
    ResourceChartDetails,
    ResourceChartImage,
    ResourceDataTable,
    ResourceFileDetails,
    ResourceMetadata,
    ResourcePreviewDetails,
    ResourceProcessing,
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
from api.services.document_processing import (
    ProcessingRefused,
    can_request_processing,
    cancel_processing,
    request_processing,
)
from api.models.ResourceProcessing import ACTIVE_STATUSES
from api.utils.enums import ProcessingStatus


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


class ProcessingStatusFilter(admin.SimpleListFilter):
    """Filter resources by their DOST-Catalyst processing state."""

    title = "processing status"
    parameter_name = "processing"
    NEVER = "never"
    STALE = "stale"

    def lookups(self, request, model_admin):
        return [
            (self.NEVER, "Never processed"),
            *ProcessingStatus.choices,
            (self.STALE, "Done, but the file changed"),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset
        if value == self.NEVER:
            return queryset.filter(processing__isnull=True)
        if value == self.STALE:
            changed = (
                ~Q(processing__source_sha256=F("resourcefiledetails__sha256"))
                | Q(resourcefiledetails__sha256__isnull=True)
                | Q(resourcefiledetails__isnull=True)
            )
            return (
                queryset.filter(processing__status=ProcessingStatus.DONE)
                .exclude(processing__source_sha256="")
                .filter(changed)
            )
        return queryset.filter(processing__status=value)


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("name", "dataset", "type", "file_format", "processing_status", "created")
    list_filter = (
        "type",
        ("resourcefiledetails__format", admin.AllValuesFieldListFilter),
        ProcessingStatusFilter,
        "dataset__organization",
        "dataset",
    )
    list_select_related = ("dataset", "resourcefiledetails", "processing")
    search_fields = ("name", "description")
    inlines = [ResourceFileDetailsInline]
    actions = ["process_documents"]

    @admin.display(description="Format", ordering="resourcefiledetails__format")
    def file_format(self, obj):
        try:
            return obj.resourcefiledetails.format
        except ObjectDoesNotExist:
            return "-"

    @admin.display(description="Processing")
    def processing_status(self, obj):
        try:
            processing = obj.processing
        except ObjectDoesNotExist:
            return "-"
        if processing.is_stale:
            return f"{processing.status} (file changed)"
        return processing.status

    def has_process_permission(self, request):
        return can_request_processing(request.user)

    @admin.action(
        description="Process selected documents with DOST-Catalyst", permissions=["process"]
    )
    def process_documents(self, request, queryset):
        requested = 0
        skipped: Counter[str] = Counter()
        for resource in queryset.select_related("resourcefiledetails"):
            try:
                request_processing(resource, request.user)
            except ProcessingRefused as exc:
                skipped[str(exc)] += 1
            else:
                requested += 1
        if requested:
            self.message_user(
                request, f"{requested} document(s) requested for processing.", messages.SUCCESS
            )
        for reason, count in skipped.items():
            self.message_user(request, f"{count} skipped: {reason}", messages.WARNING)


class ProcessedFileInline(admin.TabularInline):
    model = ProcessedFile
    extra = 0
    fields = ("kind", "file", "size", "created")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ResourceProcessing)
class ResourceProcessingAdmin(admin.ModelAdmin):
    """Requests and results; the worker writes them, so every field is read-only."""

    list_display = ("resource", "status", "requested_by", "requested_at", "finished_at")
    list_filter = ("status",)
    list_select_related = ("resource", "requested_by")
    search_fields = ("resource__name", "catalyst_job_id")
    readonly_fields = (
        "resource",
        "status",
        "options",
        "requested_by",
        "requested_at",
        "started_at",
        "finished_at",
        "catalyst_job_id",
        "cancel_requested",
        "error",
        "report",
        "source_sha256",
    )
    inlines = [ProcessedFileInline]
    actions = ["cancel_requests"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Delete removes the outputs too (rows and S3 objects); a job that waits
        # or runs must be cancelled first, or the worker loses track of it.
        if not request.user.is_superuser:
            return False
        return obj is None or not obj.is_active

    def delete_queryset(self, request, queryset):
        active = queryset.filter(status__in=ACTIVE_STATUSES)
        if active.exists():
            self.message_user(
                request,
                f"{active.count()} skipped: cancel the processing before you delete it.",
                messages.WARNING,
            )
        queryset.exclude(status__in=ACTIVE_STATUSES).delete()

    def has_cancel_permission(self, request):
        return request.user.is_superuser

    @admin.action(description="Cancel selected requests", permissions=["cancel"])
    def cancel_requests(self, request, queryset):
        cancelled = 0
        skipped: Counter[str] = Counter()
        for processing in queryset:
            try:
                cancel_processing(processing, request.user)
            except ProcessingRefused as exc:
                skipped[str(exc)] += 1
            else:
                cancelled += 1
        if cancelled:
            self.message_user(request, f"{cancelled} request(s) cancelled.", messages.SUCCESS)
        for reason, count in skipped.items():
            self.message_user(request, f"{count} skipped: {reason}", messages.WARNING)


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


class AIModelForm(forms.ModelForm):
    id = forms.IntegerField(required=False)  # makes id editable


class ModelEndpointInline(admin.TabularInline):
    model = ModelEndpoint
    extra = 1
    fields = ("url", "http_method", "auth_type", "is_primary", "is_active")


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    form = AIModelForm
    list_display = (
        "id",
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
            {"fields": ("id", "name", "display_name", "version", "description")},   # ← id added here
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

    def save_model(self, request, obj, form, change):
        """
        Allow changing the primary key ('id') by running a raw UPDATE.
        """
        if change and 'id' in form.changed_data:
            old_pk = form.initial['id']          # the id when the form was opened
            new_pk = form.cleaned_data['id']      # the new id the user entered

            # Prevent duplicate key error – check if new_pk already exists
            if AIModel.objects.filter(pk=new_pk).exclude(pk=old_pk).exists():
                raise IntegrityError(f"Primary key {new_pk} already exists.")

            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {AIModel._meta.db_table} SET id = %s WHERE id = %s",
                    [new_pk, old_pk]
                )
            # Update the in‑memory object’s pk so the admin redirect works correctly
            obj.pk = new_pk
            # No need to call save() again – the update is already applied.
        else:
            # Normal save (create or update without pk change)
            super().save_model(request, obj, form, change)

    
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
