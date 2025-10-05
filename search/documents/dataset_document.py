from typing import Any, Dict, List, Optional, Union

from django_elasticsearch_dsl import Document, Index, KeywordField, fields

from api.models import (
    Catalog,
    Dataset,
    DatasetMetadata,
    Geography,
    Metadata,
    Organization,
    Resource,
    Sector,
)
from api.utils.enums import DatasetStatus
from authorization.models import User
from DataSpace import settings
from search.documents.analysers import html_strip, ngram_analyser

INDEX = Index(settings.ELASTICSEARCH_INDEX_NAMES[__name__])
INDEX.settings(number_of_shards=1, number_of_replicas=0)


@INDEX.doc_type
class DatasetDocument(Document):
    """Elasticsearch document for Dataset model."""

    metadata = fields.NestedField(
        properties={
            "value": KeywordField(multi=True),
            "raw": KeywordField(multi=True),
            "metadata_item": fields.ObjectField(
                properties={"label": KeywordField(multi=False)}
            ),
        }
    )

    resources = fields.NestedField(
        properties={
            "name": fields.TextField(analyzer=ngram_analyser),
            "description": fields.TextField(analyzer=html_strip),
        }
    )

    title = fields.TextField(
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

    status = fields.KeywordField()

    slug = fields.KeywordField()  # Add slug field

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

    organization = fields.NestedField(
        properties={
            "name": fields.TextField(analyzer=ngram_analyser),
            "logo": fields.TextField(analyzer=ngram_analyser),
        }
    )

    user = fields.NestedField(
        properties={
            "name": fields.TextField(analyzer=ngram_analyser),
            "bio": fields.TextField(analyzer=html_strip),
            "profile_picture": fields.TextField(analyzer=ngram_analyser),
        }
    )

    formats = fields.TextField(
        attr="formats_indexing",
        analyzer=ngram_analyser,
        fields={
            "raw": fields.KeywordField(multi=True),
            "suggest": fields.CompletionField(multi=True),
        },
        multi=True,
    )

    catalogs = fields.TextField(
        attr="catalogs_indexing",
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

    is_individual_dataset = fields.BooleanField(attr="is_individual_dataset")

    has_charts = fields.BooleanField(attr="has_charts")
    download_count = fields.IntegerField(attr="download_count")
    trending_score = fields.FloatField(attr="trending_score")

    def prepare_metadata(self, instance: Dataset) -> List[Dict[str, Any]]:
        """Preprocess comma-separated metadata values into arrays."""
        processed_metadata: List[Dict[str, Any]] = []
        for meta in instance.metadata.all():  # type: DatasetMetadata
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

    def prepare_organization(self, instance: Dataset) -> Optional[Dict[str, str]]:
        """Prepare organization data for indexing, including logo URL."""
        if instance.organization:
            org = instance.organization
            logo_url = org.logo.url if org.logo else ""
            return {"name": org.name, "logo": logo_url}
        return None

    def prepare_user(self, instance: Dataset) -> Optional[Dict[str, str]]:
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

    def should_index_object(self, obj: Dataset) -> bool:
        """Check if the object should be indexed."""
        return obj.status == DatasetStatus.PUBLISHED

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
            super(DatasetDocument, self)
            .get_queryset()
            .filter(status=DatasetStatus.PUBLISHED)
        )

    def get_instances_from_related(
        self,
        related_instance: Union[
            Resource,
            Metadata,
            DatasetMetadata,
            Sector,
            Organization,
            User,
            Catalog,
            Geography,
        ],
    ) -> Optional[Union[Dataset, List[Dataset]]]:
        """Get Dataset instances from related models."""
        if isinstance(related_instance, Resource):
            return related_instance.dataset
        elif isinstance(related_instance, Metadata):
            ds_metadata_objects = related_instance.datasetmetadata_set.all()
            return [obj.dataset for obj in ds_metadata_objects]  # type: ignore
        elif isinstance(related_instance, DatasetMetadata):
            return related_instance.dataset
        elif isinstance(related_instance, Sector):
            return list(related_instance.datasets.all())
        elif isinstance(related_instance, Organization):
            return list(related_instance.datasets.all())
        elif isinstance(related_instance, User):
            return list(related_instance.datasets.all())
        elif isinstance(related_instance, Catalog):
            return list(related_instance.datasets.all())
        elif isinstance(related_instance, Geography):
            return list(related_instance.datasets.all())
        return None

    class Django:
        """Django model configuration."""

        model = Dataset

        fields = [
            "id",
            "created",
            "modified",
        ]

        related_models = [
            Resource,
            Metadata,
            DatasetMetadata,
            Sector,
            Organization,
            User,
            Catalog,
            Geography,
        ]
