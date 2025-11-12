from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.validators import URLValidator
from django.db import models

from api.utils.enums import (
    AIModelFramework,
    AIModelProvider,
    AIModelStatus,
    AIModelType,
    EndpointAuthType,
    EndpointHTTPMethod,
    HFModelClass,
)

User = get_user_model()


class AIModel(models.Model):
    """
    Registry for AI models accessed via API.
    Focuses on text-based models (translation, generation, etc.)
    """

    # Basic Information
    name = models.CharField(max_length=255, help_text="Model name or identifier")
    display_name = models.CharField(max_length=255, help_text="Human-readable name")
    version = models.CharField(max_length=50, blank=True, help_text="Model version")
    description = models.TextField(help_text="Description of the model's capabilities")

    # Model Type & Provider
    model_type = models.CharField(max_length=50, choices=AIModelType.choices)
    provider = models.CharField(max_length=50, choices=AIModelProvider.choices)
    provider_model_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Provider's model identifier (e.g., gpt-4, claude-3-opus)",
    )

    # Huggingface Models
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

    # Ownership & Organization
    organization = models.ForeignKey(
        "api.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_models",
    )
    user = models.ForeignKey(
        "authorization.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_models",
    )
    # API Configuration
    # Endpoints are stored in separate ModelEndpoint table for flexibility

    # Model Capabilities
    supports_streaming = models.BooleanField(default=False)
    max_tokens = models.IntegerField(
        null=True, blank=True, help_text="Maximum tokens supported by the model"
    )
    supported_languages = models.JSONField(
        default=list,
        help_text="List of supported language codes (e.g., ['en', 'es', 'fr'])",
    )

    # Input/Output Schema
    input_schema = models.JSONField(default=dict, help_text="Expected input format and parameters")
    output_schema = models.JSONField(default=dict, help_text="Expected output format")

    # Metadata
    tags = models.ManyToManyField("api.Tag", blank=True)
    sectors = models.ManyToManyField("api.Sector", blank=True, related_name="ai_models")
    geographies = models.ManyToManyField("api.Geography", blank=True, related_name="ai_models")
    metadata = models.JSONField(
        default=dict,
        help_text="Additional metadata (training data info, limitations, etc.)",
    )

    # Status & Visibility
    status = models.CharField(
        max_length=20, choices=AIModelStatus.choices, default=AIModelStatus.REGISTERED
    )
    is_public = models.BooleanField(
        default=False, help_text="Whether this model is publicly visible"
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this model is currently active"
    )

    # Performance Metrics (from audits)
    average_latency_ms = models.FloatField(null=True, blank=True)
    success_rate = models.FloatField(null=True, blank=True)
    last_audit_score = models.FloatField(null=True, blank=True)
    audit_count = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "is_active"]),
            models.Index(fields=["model_type", "provider"]),
            models.Index(fields=["provider", "provider_model_id"]),
        ]
        unique_together = ["user", "name", "version"]

    def __str__(self):
        return f"{self.display_name} ({self.provider})"

    @property
    def tags_indexing(self) -> list[str]:
        """Tags for indexing.

        Used in Elasticsearch indexing.
        """
        return [tag.value for tag in self.tags.all()]  # type: ignore

    @property
    def sectors_indexing(self) -> list[str]:
        """Sectors for indexing.

        Used in Elasticsearch indexing.
        """
        return [sector.name for sector in self.sectors.all()]  # type: ignore

    @property
    def geographies_indexing(self) -> list[str]:
        """Geographies for indexing.

        Used in Elasticsearch indexing.
        """
        return [geography.name for geography in self.geographies.all()]  # type: ignore

    def get_primary_endpoint(self):
        """Get the primary API endpoint for this model"""
        return self.endpoints.filter(is_primary=True).first()


class ModelEndpoint(models.Model):
    """
    API endpoints for accessing AI models.
    Supports multiple endpoints per model (e.g., different regions, fallbacks)
    """

    model = models.ForeignKey(AIModel, on_delete=models.CASCADE, related_name="endpoints")

    # Endpoint Configuration
    url = models.URLField(max_length=500, validators=[URLValidator()], help_text="API endpoint URL")
    http_method = models.CharField(
        max_length=10,
        choices=EndpointHTTPMethod.choices,
        default=EndpointHTTPMethod.POST,
    )

    # Authentication
    auth_type = models.CharField(
        max_length=20, choices=EndpointAuthType.choices, default=EndpointAuthType.BEARER
    )
    auth_header_name = models.CharField(
        max_length=100,
        default="Authorization",
        help_text="Header name for authentication (e.g., 'Authorization', 'X-API-Key')",
    )

    # Request Configuration
    headers = models.JSONField(default=dict, help_text="Additional headers to include in requests")
    request_template = models.JSONField(
        default=dict, help_text="Template for request body with placeholders"
    )
    response_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="JSON path to extract response (e.g., 'choices[0].message.content')",
    )

    # Endpoint Settings
    timeout_seconds = models.IntegerField(default=30)
    max_retries = models.IntegerField(default=3)
    is_primary = models.BooleanField(default=True, help_text="Primary endpoint to use")
    is_active = models.BooleanField(default=True)

    # Rate Limiting
    rate_limit_per_minute = models.IntegerField(
        null=True, blank=True, help_text="Rate limit for this endpoint"
    )

    # Monitoring
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    total_requests = models.IntegerField(default=0)
    failed_requests = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_primary", "-created_at"]
        indexes = [
            models.Index(fields=["model", "is_primary", "is_active"]),
        ]

    def __str__(self):
        return f"{self.model.name} - {self.url}"

    @property
    def success_rate(self):
        """Calculate success rate"""
        if self.total_requests == 0:
            return None
        return ((self.total_requests - self.failed_requests) / self.total_requests) * 100


class ModelAPIKey(models.Model):
    """
    Encrypted storage for API keys/credentials for model endpoints.
    """

    model = models.ForeignKey(AIModel, on_delete=models.CASCADE, related_name="api_keys")

    name = models.CharField(max_length=100, help_text="Friendly name for this API key")

    # Encrypted API key/token
    encrypted_key = models.BinaryField(help_text="Encrypted API key or token")

    # Key metadata
    key_type = models.CharField(
        max_length=50,
        default="api_key",
        help_text="Type of credential (api_key, bearer_token, oauth_token, etc.)",
    )

    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(
        null=True, blank=True, help_text="Expiration date for the key"
    )

    # Usage tracking
    last_used_at = models.DateTimeField(null=True, blank=True)
    usage_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Model API Key"
        verbose_name_plural = "Model API Keys"

    def __str__(self):
        return f"{self.model.name} - {self.name}"

    def set_key(self, plain_key: str):
        """Encrypt and store the API key"""
        # In production, use Django's SECRET_KEY or a dedicated encryption key
        # For now, we'll use a simple approach
        import base64

        from django.conf import settings

        # This is a simplified encryption - in production use proper key management
        cipher_suite = Fernet(self._get_encryption_key())
        self.encrypted_key = cipher_suite.encrypt(plain_key.encode())

    def get_key(self) -> str:
        """Decrypt and return the API key"""
        cipher_suite = Fernet(self._get_encryption_key())
        return cipher_suite.decrypt(self.encrypted_key).decode()

    @staticmethod
    def _get_encryption_key():
        """Get or generate encryption key"""
        # In production, store this securely in environment variables
        # This is a simplified version
        import base64

        from django.conf import settings

        # Use first 32 bytes of SECRET_KEY, base64 encoded
        key = settings.SECRET_KEY[:32].encode()
        return base64.urlsafe_b64encode(key.ljust(32)[:32])
