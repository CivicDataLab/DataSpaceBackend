"""Elasticsearch document for AIModel."""

from typing import Any, Dict, List, Optional, Union

from django_elasticsearch_dsl import Document, Index, KeywordField, fields

from api.models.AIModel import AIModel, ModelEndpoint
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

    # Model configuration
    model_type = fields.KeywordField()
    provider = fields.KeywordField()
    provider_model_id = fields.KeywordField()

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

    # Supported languages (stored as JSON array in model)
    supported_languages = fields.KeywordField(multi=True)

    # Capabilities
    supports_streaming = fields.BooleanField()
    max_tokens = fields.IntegerField()

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

    # Computed fields
    is_individual_model = fields.BooleanField()
    has_active_endpoints = fields.BooleanField()
    endpoint_count = fields.IntegerField()

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
                    instance.user.profile_picture.url
                    if instance.user.profile_picture
                    else ""
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
            ModelEndpoint, Organization, User, Tag, Sector, Geography
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
        ]
