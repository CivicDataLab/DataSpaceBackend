"""Elasticsearch document for AIModel."""

from typing import Any, Dict, List, Optional, Union

from django_elasticsearch_dsl import Document, Index, KeywordField, fields

from api.models.AIModel import AIModel, ModelEndpoint
from api.models.AIModelVersion import AIModelVersion, VersionProvider
from api.models.Dataset import Tag
from api.models.Geography import Geography
from api.models.Organization import Organization
from api.models.Sector import Sector
from api.utils.enums import AIModelStatus
from authorization.models import User
from DataSpace import settings
from search.documents.analysers import html_strip, ngram_analyser

INDEX = Index(settings.ELASTICSEARCH_INDEX_NAMES[__name__])
INDEX.settings(number_of_shards=1, number_of_replicas=0)


@INDEX.doc_type
class AIModelDocument(Document):
    """Elasticsearch document for AIModel."""

    # Basic fields with analyzers
    name = fields.TextField(
        analyzer=ngram_analyser,
        fields={
            "raw": KeywordField(multi=False),
        },
    )

    display_name = fields.TextField(
        analyzer=ngram_analyser,
        fields={
            "raw": KeywordField(multi=False),
        },
    )

    description = fields.TextField(
        analyzer=html_strip,
        fields={
            "raw": fields.TextField(analyzer="keyword"),
        },
    )

    version = fields.KeywordField()
    provider = fields.KeywordField()
    provider_model_id = fields.KeywordField()
    supported_languages = fields.KeywordField(multi=True)
    supports_streaming = fields.BooleanField()
    max_tokens = fields.IntegerField()

    # Model configuration
    model_type = fields.KeywordField()

    # Status and visibility
    status = fields.KeywordField()
    is_public = fields.BooleanField()
    is_active = fields.BooleanField()

    # Tags (ManyToMany relationship)
    tags = fields.TextField(
        attr="tags_indexing",
        analyzer=ngram_analyser,
        fields={
            "raw": fields.KeywordField(multi=True),
            "suggest": fields.CompletionField(multi=True),
        },
        multi=True,
    )

    # Sectors (ManyToMany relationship)
    sectors = fields.TextField(
        attr="sectors_indexing",
        analyzer=ngram_analyser,
        fields={
            "raw": fields.KeywordField(multi=True),
            "suggest": fields.CompletionField(multi=True),
        },
        multi=True,
    )

    # Geographies (ManyToMany relationship)
    geographies = fields.TextField(
        attr="geographies_indexing",
        analyzer=ngram_analyser,
        fields={
            "raw": fields.KeywordField(multi=True),
            "suggest": fields.CompletionField(multi=True),
        },
        multi=True,
    )

    # Performance metrics
    average_latency_ms = fields.FloatField()
    success_rate = fields.FloatField()
    last_audit_score = fields.FloatField()
    audit_count = fields.IntegerField()

    # Organization relationship
    organization = fields.NestedField(
        properties={
            "name": fields.TextField(analyzer=ngram_analyser),
            "logo": fields.TextField(analyzer=ngram_analyser),
        }
    )

    # User relationship
    user = fields.NestedField(
        properties={
            "name": fields.TextField(analyzer=ngram_analyser),
            "bio": fields.TextField(analyzer=html_strip),
            "profile_picture": fields.TextField(analyzer=ngram_analyser),
        }
    )

    # Endpoints nested field
    endpoints = fields.NestedField(
        properties={
            "url": fields.KeywordField(),
            "http_method": fields.KeywordField(),
            "auth_type": fields.KeywordField(),
            "is_primary": fields.BooleanField(),
            "is_active": fields.BooleanField(),
        }
    )

    versions = fields.NestedField(
        properties={
            "id": fields.IntegerField(),
            "version": fields.KeywordField(),
            "version_notes": fields.TextField(analyzer=html_strip),
            "lifecycle_stage": fields.KeywordField(),
            "is_latest": fields.BooleanField(),
            "status": fields.KeywordField(),
            "supports_streaming": fields.BooleanField(),
            "max_tokens": fields.IntegerField(),
            "supported_languages": fields.KeywordField(multi=True),
            "created_at": fields.DateField(),
            "updated_at": fields.DateField(),
            "providers": fields.NestedField(
                properties={
                    "id": fields.IntegerField(),
                    "provider": fields.KeywordField(),
                    "provider_model_id": fields.KeywordField(),
                    "is_primary": fields.BooleanField(),
                    "is_active": fields.BooleanField(),
                    # API Configuration
                    "api_endpoint_url": fields.KeywordField(),
                    "api_http_method": fields.KeywordField(),
                    "api_timeout_seconds": fields.IntegerField(),
                    "api_auth_type": fields.KeywordField(),
                    # HuggingFace Configuration
                    "hf_use_pipeline": fields.BooleanField(),
                    "hf_model_class": fields.KeywordField(),
                    "framework": fields.KeywordField(),
                }
            ),
        }
    )

    # Computed fields
    is_individual_model = fields.BooleanField()
    has_active_endpoints = fields.BooleanField()
    endpoint_count = fields.IntegerField()
    version_count = fields.IntegerField()
    lifecycle_stage = fields.KeywordField()  # Primary version's lifecycle stage
    all_providers = fields.KeywordField(multi=True)  # All unique providers across versions

    def prepare_organization(self, instance: AIModel) -> Optional[Dict[str, str]]:
        """Prepare organization data for indexing, including logo URL."""
        if instance.organization:
            org = instance.organization
            logo_url = org.logo.url if org.logo else ""
            return {"name": org.name, "logo": logo_url}
        return None

    def prepare_user(self, instance: AIModel) -> Optional[Dict[str, str]]:
        """Prepare user data for indexing."""
        if instance.user:
            return {
                "name": instance.user.full_name,
                "bio": instance.user.bio or "",
                "profile_picture": (
                    instance.user.profile_picture.url if instance.user.profile_picture else ""
                ),
            }
        return None

    def prepare_endpoints(self, instance: AIModel) -> List[Dict[str, Any]]:
        """Prepare endpoints data for indexing."""
        endpoints = []
        for endpoint in instance.endpoints.all():
            endpoints.append(
                {
                    "url": endpoint.url,  # type: ignore
                    "http_method": endpoint.http_method,  # type: ignore
                    "auth_type": endpoint.auth_type,  # type: ignore
                    "is_primary": endpoint.is_primary,  # type: ignore
                    "is_active": endpoint.is_active,  # type: ignore
                }
            )
        return endpoints

    def prepare_is_individual_model(self, instance: AIModel) -> bool:
        """Check if the model is created by an individual."""
        return instance.organization is None and instance.user is not None

    def prepare_has_active_endpoints(self, instance: AIModel) -> bool:
        """Check if the model has any active endpoints."""
        return instance.endpoints.filter(is_active=True).exists()

    def prepare_endpoint_count(self, instance: AIModel) -> int:
        """Count the number of endpoints."""
        return instance.endpoints.count()

    def prepare_versions(self, instance: AIModel) -> List[Dict[str, Any]]:
        """Prepare versions data for indexing."""
        versions_data: List[Dict[str, Any]] = []
        for version in instance.versions.all():  # type: ignore[attr-defined]
            version_obj: AIModelVersion = version  # type: ignore[assignment]
            providers_data: List[Dict[str, Any]] = []
            for provider in version_obj.providers.all():  # type: ignore[attr-defined]
                provider_obj: VersionProvider = provider  # type: ignore[assignment]
                providers_data.append(
                    {
                        "id": provider_obj.id,
                        "provider": provider_obj.provider,
                        "provider_model_id": provider_obj.provider_model_id,
                        "is_primary": provider_obj.is_primary,
                        "is_active": provider_obj.is_active,
                        # API Configuration
                        "api_endpoint_url": provider_obj.api_endpoint_url,
                        "api_http_method": provider_obj.api_http_method,
                        "api_timeout_seconds": provider_obj.api_timeout_seconds,
                        "api_auth_type": provider_obj.api_auth_type,
                        # HuggingFace Configuration
                        "hf_use_pipeline": provider_obj.hf_use_pipeline,
                        "hf_model_class": provider_obj.hf_model_class,
                        "framework": provider_obj.framework,
                    }
                )
            versions_data.append(
                {
                    "id": version_obj.id,
                    "version": version_obj.version,
                    "version_notes": version_obj.version_notes or "",
                    "lifecycle_stage": version_obj.lifecycle_stage,
                    "is_latest": version_obj.is_latest,
                    "status": version_obj.status,
                    "supports_streaming": version_obj.supports_streaming,
                    "max_tokens": version_obj.max_tokens,
                    "supported_languages": version_obj.supported_languages or [],
                    "created_at": version_obj.created_at,
                    "updated_at": version_obj.updated_at,
                    "providers": providers_data,
                }
            )
        return versions_data

    def _get_primary_version(self, instance: AIModel) -> Optional[AIModelVersion]:
        """Get the primary (latest) version of the model."""
        primary = instance.versions.filter(is_latest=True).first()  # type: ignore[attr-defined]
        if not primary:
            primary = instance.versions.first()  # type: ignore[attr-defined]
        return primary  # type: ignore[return-value]

    def _get_primary_provider(self, version: Optional[AIModelVersion]) -> Optional[VersionProvider]:
        """Get the primary provider of a version."""
        if not version:
            return None
        primary = version.providers.filter(is_primary=True).first()  # type: ignore[attr-defined]
        if not primary:
            primary = version.providers.first()  # type: ignore[attr-defined]
        return primary  # type: ignore[return-value]

    def prepare_version(self, instance: AIModel) -> str:
        """Prepare version from primary version for backward compatibility."""
        primary_version = self._get_primary_version(instance)
        if primary_version:
            return str(primary_version.version)
        # Fallback to legacy field on AIModel
        return instance.version or ""

    def prepare_provider(self, instance: AIModel) -> str:
        """Prepare provider from primary version's primary provider for backward compatibility."""
        primary_version = self._get_primary_version(instance)
        primary_provider = self._get_primary_provider(primary_version)
        if primary_provider:
            return str(primary_provider.provider)
        # Fallback to legacy field on AIModel
        return instance.provider or ""

    def prepare_provider_model_id(self, instance: AIModel) -> str:
        """Prepare provider_model_id from primary version's primary provider."""
        primary_version = self._get_primary_version(instance)
        primary_provider = self._get_primary_provider(primary_version)
        if primary_provider:
            return primary_provider.provider_model_id or ""
        # Fallback to legacy field on AIModel
        return instance.provider_model_id or ""

    def prepare_supported_languages(self, instance: AIModel) -> List[str]:
        """Prepare supported_languages from primary version."""
        primary_version = self._get_primary_version(instance)
        if primary_version and primary_version.supported_languages:
            return list(primary_version.supported_languages)
        # Fallback to legacy field on AIModel
        return list(instance.supported_languages or [])

    def prepare_supports_streaming(self, instance: AIModel) -> bool:
        """Prepare supports_streaming from primary version."""
        primary_version = self._get_primary_version(instance)
        if primary_version:
            return bool(primary_version.supports_streaming)
        # Fallback to legacy field on AIModel
        return bool(instance.supports_streaming)

    def prepare_max_tokens(self, instance: AIModel) -> Optional[int]:
        """Prepare max_tokens from primary version."""
        primary_version = self._get_primary_version(instance)
        if primary_version and primary_version.max_tokens:
            return int(primary_version.max_tokens)
        # Fallback to legacy field on AIModel
        return instance.max_tokens

    def prepare_version_count(self, instance: AIModel) -> int:
        """Count the number of versions."""
        return instance.versions.count()  # type: ignore[attr-defined]

    def prepare_lifecycle_stage(self, instance: AIModel) -> str:
        """Get lifecycle stage from primary version."""
        primary_version = self._get_primary_version(instance)
        if primary_version:
            return str(primary_version.lifecycle_stage)
        return "DEVELOPMENT"

    def prepare_all_providers(self, instance: AIModel) -> List[str]:
        """Get all unique providers across all versions."""
        providers: set[str] = set()
        for version in instance.versions.all():  # type: ignore[attr-defined]
            version_obj: AIModelVersion = version  # type: ignore[assignment]
            for provider in version_obj.providers.all():  # type: ignore[attr-defined]
                provider_obj: VersionProvider = provider  # type: ignore[assignment]
                providers.add(str(provider_obj.provider))
        # Also include legacy provider if set
        if instance.provider:
            providers.add(str(instance.provider))
        return list(providers)

    def should_index_object(self, obj: AIModel) -> bool:
        """
        Check if the object should be indexed.
        Only index public and active models, or approved models.
        """
        return (
            obj.is_public
            and obj.is_active
            and obj.status
            in [
                AIModelStatus.ACTIVE,
                AIModelStatus.APPROVED,
            ]
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the document to Elasticsearch index."""
        if self.should_index_object(self.to_dict()):  # type: ignore
            super().save(*args, **kwargs)
        else:
            self.delete(ignore=404)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Remove the document from Elasticsearch index."""
        super().delete(*args, **kwargs)

    def get_queryset(self) -> Any:
        """Get the queryset for indexing - only public, active, and approved/active models."""
        return (
            super(AIModelDocument, self)
            .get_queryset()
            .filter(
                is_public=True,
                is_active=True,
                status__in=[AIModelStatus.ACTIVE, AIModelStatus.APPROVED],
            )
        )

    def get_instances_from_related(
        self,
        related_instance: Union[
            ModelEndpoint,
            Organization,
            User,
            Tag,
            Sector,
            Geography,
            AIModelVersion,
            VersionProvider,
        ],
    ) -> Optional[Union[AIModel, List[AIModel]]]:
        """Get AIModel instances from related models."""
        if isinstance(related_instance, ModelEndpoint):
            return related_instance.model
        elif isinstance(related_instance, Organization):
            return list(related_instance.ai_models.all())
        elif isinstance(related_instance, User):
            return list(related_instance.ai_models.all())
        elif isinstance(related_instance, Tag):
            return list(related_instance.aimodel_set.all())
        elif isinstance(related_instance, Sector):
            return list(related_instance.ai_models.all())
        elif isinstance(related_instance, Geography):
            return list(related_instance.ai_models.all())
        elif isinstance(related_instance, AIModelVersion):
            return related_instance.ai_model
        elif isinstance(related_instance, VersionProvider):
            return related_instance.version.ai_model
        return None

    class Django:
        """Django model configuration."""

        model = AIModel

        fields = [
            "id",
            "created_at",
            "updated_at",
            "last_tested_at",
        ]

        related_models = [
            ModelEndpoint,
            Organization,
            User,
            Tag,
            Sector,
            Geography,
            AIModelVersion,
            VersionProvider,
        ]
