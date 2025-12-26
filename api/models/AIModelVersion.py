"""AI Model Version model for version-specific configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from api.utils.enums import AIModelLifecycleStage, AIModelStatus

if TYPE_CHECKING:
    from django.db.models import QuerySet


class AIModelVersion(models.Model):
    """
    Version of an AI Model with its own configuration.
    Each version can have multiple providers.
    """

    ai_model = models.ForeignKey(
        "api.AIModel",
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.CharField(max_length=50, help_text="Version number (e.g., 1.0.0)")
    version_notes = models.TextField(blank=True, help_text="Changelog/notes for this version")

    # Version-specific capabilities
    supports_streaming = models.BooleanField(default=False)
    max_tokens = models.IntegerField(null=True, blank=True, help_text="Maximum tokens supported")
    supported_languages = models.JSONField(
        default=list, help_text="List of supported language codes"
    )
    input_schema = models.JSONField(default=dict, help_text="Expected input format and parameters")
    output_schema = models.JSONField(default=dict, help_text="Expected output format")
    metadata = models.JSONField(default=dict, help_text="Additional version-specific metadata")

    # Status & Lifecycle
    status = models.CharField(
        max_length=20,
        choices=AIModelStatus.choices,
        default=AIModelStatus.REGISTERED,
    )
    lifecycle_stage = models.CharField(
        max_length=20,
        choices=AIModelLifecycleStage.choices,
        default=AIModelLifecycleStage.DEVELOPMENT,
        help_text="Current lifecycle stage of this version",
    )
    is_latest = models.BooleanField(default=False, help_text="Whether this is the latest version")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["ai_model", "version"]
        ordering = ["-created_at"]
        verbose_name = "AI Model Version"
        verbose_name_plural = "AI Model Versions"

    def __str__(self):
        return f"{self.ai_model.name} v{self.version}"

    def save(self, *args, **kwargs):
        # If this is set as latest, unset others
        if self.is_latest:
            AIModelVersion.objects.filter(ai_model=self.ai_model, is_latest=True).exclude(
                pk=self.pk
            ).update(is_latest=False)
        super().save(*args, **kwargs)

    def copy_providers_from(self, source_version: AIModelVersion) -> None:
        """
        Copy all providers from another version.
        Used when creating a new version.
        """
        for provider in source_version.providers.all():  # type: ignore[attr-defined]
            # Create a copy of the provider
            VersionProvider.objects.create(
                version=self,
                provider=provider.provider,  # type: ignore[attr-defined]
                provider_model_id=provider.provider_model_id,  # type: ignore[attr-defined]
                is_primary=provider.is_primary,  # type: ignore[attr-defined]
                is_active=provider.is_active,  # type: ignore[attr-defined]
                hf_use_pipeline=provider.hf_use_pipeline,  # type: ignore[attr-defined]
                hf_auth_token=provider.hf_auth_token,  # type: ignore[attr-defined]
                hf_model_class=provider.hf_model_class,  # type: ignore[attr-defined]
                hf_attn_implementation=provider.hf_attn_implementation,  # type: ignore[attr-defined]
                framework=provider.framework,  # type: ignore[attr-defined]
                config=provider.config,  # type: ignore[attr-defined]
            )


class VersionProvider(models.Model):
    """
    Provider configuration for a specific version.
    A version can have multiple providers (HF, Custom, OpenAI, etc.)
    Only ONE can be primary per version.
    """

    from api.utils.enums import AIModelFramework, AIModelProvider, HFModelClass

    version = models.ForeignKey(
        AIModelVersion,
        on_delete=models.CASCADE,
        related_name="providers",
    )

    # Provider info
    provider = models.CharField(max_length=50, choices=AIModelProvider.choices)
    provider_model_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Provider's model identifier (e.g., gpt-4, claude-3-opus)",
    )
    is_primary = models.BooleanField(
        default=False, help_text="Whether this is the primary provider for the version"
    )
    is_active = models.BooleanField(default=True)

    # Huggingface-specific fields
    hf_use_pipeline = models.BooleanField(default=False, help_text="Use Pipeline inference API")
    hf_auth_token = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Huggingface Auth Token for gated models",
    )
    hf_model_class = models.CharField(
        max_length=100,
        choices=HFModelClass.choices,
        blank=True,
        null=True,
        help_text="Specify model head to use",
    )
    hf_attn_implementation = models.CharField(
        max_length=255,
        blank=True,
        default="flash_attention_2",
        help_text="Attention Function",
    )
    framework = models.CharField(
        max_length=10,
        choices=AIModelFramework.choices,
        blank=True,
        null=True,
        help_text="Framework (PyTorch or TensorFlow)",
    )

    # Provider-specific configuration
    config = models.JSONField(default=dict, help_text="Provider-specific configuration")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_primary", "-created_at"]
        verbose_name = "Version Provider"
        verbose_name_plural = "Version Providers"

    def __str__(self):
        primary_str = " (Primary)" if self.is_primary else ""
        return f"{self.version} - {self.provider}{primary_str}"

    def save(self, *args, **kwargs):
        # Ensure only one primary per version
        if self.is_primary:
            VersionProvider.objects.filter(version=self.version, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)
        super().save(*args, **kwargs)
