from typing import Any, Dict, List, Optional, Union

from django_elasticsearch_dsl import Document, Index, KeywordField, fields

from api.models import (
    Dataset,
    Geography,
    Metadata,
    Organization,
    Sector,
    UseCase,
    UseCaseMetadata,
)
from api.utils.enums import UseCaseStatus
from authorization.models import User
from DataSpace import settings
from search.documents.analysers import html_strip, ngram_analyser

INDEX = Index(settings.ELASTICSEARCH_INDEX_NAMES[__name__])
INDEX.settings(number_of_shards=1, number_of_replicas=0)


@INDEX.doc_type
class UseCaseDocument(Document):
    """Elasticsearch document for UseCase model."""

    metadata = fields.NestedField(
        properties={
            "value": KeywordField(multi=True),
            "raw": KeywordField(multi=True),
            "metadata_item": fields.ObjectField(
                properties={"label": KeywordField(multi=False)}
            ),
        }
    )

    datasets = fields.NestedField(
        properties={
            "title": fields.TextField(analyzer=ngram_analyser),
            "description": fields.TextField(analyzer=html_strip),
            "slug": fields.KeywordField(),
        }
    )

    title = fields.TextField(
        analyzer=ngram_analyser,
        fields={
            "raw": KeywordField(multi=False),
        },
    )

    summary = fields.TextField(
        analyzer=html_strip,
        fields={
            "raw": fields.TextField(analyzer="keyword"),
        },
    )

    logo = fields.TextField(analyzer=ngram_analyser)

    status = fields.KeywordField()

    running_status = fields.KeywordField()

    slug = fields.KeywordField()

    tags = fields.TextField(
        attr="tags_indexing",
        analyzer=ngram_analyser,
        fields={
            "raw": fields.KeywordField(multi=True),
            "suggest": fields.CompletionField(multi=True),
        },
        multi=True,
    )

    sectors = fields.TextField(
        attr="sectors_indexing",
        analyzer=ngram_analyser,
        fields={
            "raw": fields.KeywordField(multi=True),
            "suggest": fields.CompletionField(multi=True),
        },
        multi=True,
    )

    geographies = fields.TextField(
        attr="geographies_indexing",
        analyzer=ngram_analyser,
        fields={
            "raw": fields.KeywordField(multi=True),
            "suggest": fields.CompletionField(multi=True),
        },
        multi=True,
    )

    organization = fields.NestedField(
        properties={
            "name": fields.TextField(
                analyzer=ngram_analyser, fields={"raw": fields.KeywordField()}
            ),
            "logo": fields.TextField(analyzer=ngram_analyser),
        }
    )

    user = fields.NestedField(
        properties={
            "name": fields.TextField(
                analyzer=ngram_analyser, fields={"raw": fields.KeywordField()}
            ),
            "bio": fields.TextField(analyzer=html_strip),
            "profile_picture": fields.TextField(analyzer=ngram_analyser),
        }
    )

    contributors = fields.NestedField(
        properties={
            "name": fields.TextField(
                analyzer=ngram_analyser, fields={"raw": fields.KeywordField()}
            ),
            "bio": fields.TextField(analyzer=html_strip),
            "profile_picture": fields.TextField(analyzer=ngram_analyser),
        }
    )

    organizations = fields.NestedField(
        properties={
            "name": fields.TextField(
                analyzer=ngram_analyser, fields={"raw": fields.KeywordField()}
            ),
            "logo": fields.TextField(analyzer=ngram_analyser),
            "relationship_type": fields.KeywordField(),
        }
    )

    is_individual_usecase = fields.BooleanField(attr="is_individual_usecase")

    website = fields.TextField(analyzer=ngram_analyser)
    contact_email = fields.KeywordField()
    platform_url = fields.TextField(analyzer=ngram_analyser)
    started_on = fields.DateField()
    completed_on = fields.DateField()

    def prepare_metadata(self, instance: UseCase) -> List[Dict[str, Any]]:
        """Preprocess comma-separated metadata values into arrays."""
        processed_metadata: List[Dict[str, Any]] = []
        for meta in instance.metadata.all():  # type: UseCaseMetadata
            # Skip if metadata_item is None (orphaned metadata)
            if not meta.metadata_item:
                continue

            value_list = (
                [val.strip() for val in meta.value.split(",")]
                if "," in meta.value
                else [meta.value]
            )
            processed_metadata.append(
                {
                    "value": value_list,
                    "metadata_item": {"label": meta.metadata_item.label},
                }
            )
        return processed_metadata

    def prepare_datasets(self, instance: UseCase) -> List[Dict[str, str]]:
        """Prepare datasets data for indexing."""
        datasets_data = []
        for dataset in instance.datasets.all():
            datasets_data.append(
                {
                    "title": dataset.title or "",  # type: ignore
                    "description": dataset.description or "",  # type: ignore
                    "slug": dataset.slug or "",  # type: ignore
                }
            )
        return datasets_data

    def prepare_organization(self, instance: UseCase) -> Optional[Dict[str, str]]:
        """Prepare organization data for indexing, including logo URL."""
        if instance.organization:
            org = instance.organization
            logo_url = org.logo.url if org.logo else ""
            return {"name": org.name, "logo": logo_url}
        return None

    def prepare_user(self, instance: UseCase) -> Optional[Dict[str, str]]:
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

    def prepare_contributors(self, instance: UseCase) -> List[Dict[str, str]]:
        """Prepare contributors data for indexing."""
        contributors_data = []
        for contributor in instance.contributors.all():
            contributors_data.append(
                {
                    "name": contributor.full_name,  # type: ignore
                    "bio": contributor.bio or "",  # type: ignore
                    "profile_picture": (
                        contributor.profile_picture.url  # type: ignore
                        if contributor.profile_picture  # type: ignore
                        else ""
                    ),
                }
            )
        return contributors_data

    def prepare_organizations(self, instance: UseCase) -> List[Dict[str, str]]:
        """Prepare related organizations data for indexing."""
        organizations_data = []
        for relationship in instance.usecaseorganizationrelationship_set.all():
            org = relationship.organization  # type: ignore
            logo_url = org.logo.url if org.logo else ""  # type: ignore
            organizations_data.append(
                {
                    "name": org.name,  # type: ignore
                    "logo": logo_url,
                    "relationship_type": relationship.relationship_type,  # type: ignore
                }
            )
        return organizations_data

    def prepare_logo(self, instance: UseCase) -> str:
        """Prepare logo URL for indexing."""
        if instance.logo:
            return str(instance.logo.path.replace("/code/files/", ""))
        return ""

    def should_index_object(self, obj: UseCase) -> bool:
        """Check if the object should be indexed."""
        return obj.status == UseCaseStatus.PUBLISHED

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save the document to Elasticsearch index."""
        if self.status == "PUBLISHED":
            super().save(*args, **kwargs)
        else:
            self.delete(ignore=404)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Remove the document from Elasticsearch index."""
        super().delete(*args, **kwargs)

    def get_queryset(self) -> Any:
        """Get the queryset for indexing."""
        return (
            super(UseCaseDocument, self)
            .get_queryset()
            .filter(status=UseCaseStatus.PUBLISHED)
        )

    def get_instances_from_related(
        self,
        related_instance: Union[
            Dataset, Metadata, UseCaseMetadata, Sector, Organization, User, Geography
        ],
    ) -> Optional[Union[UseCase, List[UseCase]]]:
        """Get UseCase instances from related models."""
        if isinstance(related_instance, Dataset):
            return list(related_instance.usecase_set.all())
        elif isinstance(related_instance, Metadata):
            uc_metadata_objects = related_instance.usecasemetadata_set.all()
            return [obj.usecase for obj in uc_metadata_objects]  # type: ignore
        elif isinstance(related_instance, UseCaseMetadata):
            return related_instance.usecase
        elif isinstance(related_instance, Sector):
            return list(related_instance.usecases.all())
        elif isinstance(related_instance, Organization):
            # Get usecases where this org is the primary organization
            primary_usecases = list(related_instance.usecase_set.all())
            # Get usecases where this org is related through the relationship model
            related_usecases = list(related_instance.related_usecases.all())
            return primary_usecases + related_usecases
        elif isinstance(related_instance, User):
            # Get usecases where this user is the owner
            owned_usecases = list(related_instance.usecase_set.all())
            # Get usecases where this user is a contributor
            contributed_usecases = list(related_instance.contributed_usecases.all())
            return owned_usecases + contributed_usecases
        elif isinstance(related_instance, Geography):
            return list(related_instance.usecases.all())
        return None

    class Django:
        """Django model configuration."""

        model = UseCase

        fields = [
            "id",
            "created",
            "modified",
        ]

        related_models = [
            Dataset,
            Metadata,
            UseCaseMetadata,
            Sector,
            Organization,
            User,
            Geography,
        ]
