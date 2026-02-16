from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from django_elasticsearch_dsl import Document, Index, KeywordField, fields

from api.models import (
    Collaborative,
    CollaborativeMetadata,
    CollaborativeOrganizationRelationship,
    Dataset,
    Geography,
    Metadata,
    Organization,
    Sector,
    UseCase,
)
from api.utils.enums import CollaborativeStatus
from authorization.models import User
from DataSpace import settings
from search.documents.analysers import html_strip, ngram_analyser

if TYPE_CHECKING:
    from api.models import CollaborativeOrganizationRelationship as RelationshipModel
    from api.models import Dataset as DatasetModel
    from api.models import Organization as OrganizationModel
    from api.models import UseCase as UseCaseModel

INDEX = Index(settings.ELASTICSEARCH_INDEX_NAMES[__name__])
INDEX.settings(number_of_shards=1, number_of_replicas=0)


@INDEX.doc_type
class CollaborativeDocument(Document):
    """Elasticsearch document for Collaborative model."""

    metadata = fields.NestedField(
        properties={
            "value": KeywordField(multi=True),
            "raw": KeywordField(multi=True),
            "metadata_item": fields.ObjectField(properties={"label": KeywordField(multi=False)}),
        }
    )

    datasets = fields.NestedField(
        properties={
            "title": fields.TextField(analyzer=ngram_analyser),
            "description": fields.TextField(analyzer=html_strip),
            "slug": fields.KeywordField(),
        }
    )

    use_cases = fields.NestedField(
        properties={
            "title": fields.TextField(analyzer=ngram_analyser),
            "summary": fields.TextField(analyzer=html_strip),
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
    cover_image = fields.TextField(analyzer=ngram_analyser)

    status = fields.KeywordField()
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

    is_individual_collaborative = fields.BooleanField(attr="is_individual_collaborative")

    website = fields.TextField(analyzer=ngram_analyser)
    contact_email = fields.KeywordField()
    platform_url = fields.TextField(analyzer=ngram_analyser)
    started_on = fields.DateField()
    completed_on = fields.DateField()

    def prepare_metadata(self, instance: Collaborative) -> List[Dict[str, Any]]:
        processed_metadata: List[Dict[str, Any]] = []
        for meta in instance.metadata.all():  # type: CollaborativeMetadata
            if not meta.metadata_item:
                continue

            value_list = (
                [val.strip() for val in meta.value.split(",")]
                if isinstance(meta.value, str) and "," in meta.value
                else [meta.value]
            )
            processed_metadata.append(
                {
                    "value": value_list,
                    "metadata_item": {"label": meta.metadata_item.label},
                }
            )
        return processed_metadata

    def prepare_datasets(self, instance: Collaborative) -> List[Dict[str, str]]:
        datasets_data: List[Dict[str, str]] = []
        for dataset in instance.datasets.all():
            datasets_data.append(
                {
                    "title": dataset.title or "",  # type: ignore[attr-defined]
                    "description": dataset.description or "",  # type: ignore[attr-defined]
                    "slug": dataset.slug or "",  # type: ignore[attr-defined]
                }
            )
        return datasets_data

    def prepare_use_cases(self, instance: Collaborative) -> List[Dict[str, str]]:
        use_cases_data: List[Dict[str, str]] = []
        for use_case in instance.use_cases.all():
            use_cases_data.append(
                {
                    "title": use_case.title or "",  # type: ignore[attr-defined]
                    "summary": use_case.summary or "",  # type: ignore[attr-defined]
                    "slug": use_case.slug or "",  # type: ignore[attr-defined]
                }
            )
        return use_cases_data

    def prepare_organization(self, instance: Collaborative) -> Optional[Dict[str, str]]:
        if instance.organization:
            org = instance.organization
            logo_url = org.logo.url if org.logo else ""
            return {"name": org.name, "logo": logo_url}
        return None

    def prepare_user(self, instance: Collaborative) -> Optional[Dict[str, str]]:
        if instance.user:
            return {
                "name": instance.user.full_name,
                "bio": instance.user.bio or "",
                "profile_picture": (
                    instance.user.profile_picture.url if instance.user.profile_picture else ""
                ),
            }
        return None

    def prepare_contributors(self, instance: Collaborative) -> List[Dict[str, str]]:
        contributors_data: List[Dict[str, str]] = []
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

    def prepare_organizations(self, instance: Collaborative) -> List[Dict[str, str]]:
        organizations_data: List[Dict[str, str]] = []
        relationships = CollaborativeOrganizationRelationship.objects.filter(collaborative=instance)
        for relationship in relationships:
            org = relationship.organization  # type: ignore[attr-defined]
            logo_url = org.logo.url if org.logo else ""
            organizations_data.append(
                {
                    "name": org.name,  # type: ignore[attr-defined]
                    "logo": logo_url,
                    "relationship_type": relationship.relationship_type,  # type: ignore[attr-defined]
                }
            )
        return organizations_data

    def prepare_logo(self, instance: Collaborative) -> str:
        if instance.logo:
            return str(instance.logo.path.replace("/code/files/", ""))
        return ""

    def prepare_cover_image(self, instance: Collaborative) -> str:
        if instance.cover_image:
            return str(instance.cover_image.path.replace("/code/files/", ""))
        return ""

    def should_index_object(self, obj: Collaborative) -> bool:
        return obj.status == CollaborativeStatus.PUBLISHED

    def save(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - thin wrapper
        if self.status == CollaborativeStatus.PUBLISHED:
            super().save(*args, **kwargs)
        else:
            self.delete(ignore=404)

    def delete(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - thin wrapper
        super().delete(*args, **kwargs)

    def get_queryset(self) -> Any:
        return (
            super(CollaborativeDocument, self)
            .get_queryset()
            .filter(status=CollaborativeStatus.PUBLISHED)
        )

    def get_instances_from_related(
        self,
        related_instance: Union[
            Dataset,
            UseCase,
            Metadata,
            CollaborativeMetadata,
            Sector,
            Organization,
            User,
            Geography,
        ],
    ) -> Optional[Union[Collaborative, List[Collaborative]]]:
        if isinstance(related_instance, Dataset):
            return list(related_instance.collaborative_set.all())  # type: ignore[attr-defined]
        if isinstance(related_instance, UseCase):
            return list(related_instance.collaborative_set.all())  # type: ignore[attr-defined]
        if isinstance(related_instance, Metadata):
            collab_metadata_objects = related_instance.collaborativemetadata_set.all()  # type: ignore[attr-defined]
            return [obj.collaborative for obj in collab_metadata_objects]  # type: ignore[attr-defined]
        if isinstance(related_instance, CollaborativeMetadata):
            return related_instance.collaborative  # type: ignore[attr-defined]
        if isinstance(related_instance, Sector):
            return list(related_instance.collaboratives.all())
        if isinstance(related_instance, Organization):
            primary = list(related_instance.collaborative_set.all())
            related = list(related_instance.related_collaboratives.all())
            return primary + related
        if isinstance(related_instance, User):
            owned = list(related_instance.collaborative_set.all())
            contributed = list(related_instance.contributed_collaboratives.all())
            return owned + contributed
        if isinstance(related_instance, Geography):
            return list(related_instance.collaboratives.all())
        return None

    class Django:
        model = Collaborative

        fields = [
            "id",
            "created",
            "modified",
        ]

        related_models = [
            Dataset,
            UseCase,
            Metadata,
            CollaborativeMetadata,
            Sector,
            Organization,
            User,
            Geography,
        ]
