"""Elasticsearch document for Publication (UI "Resource").

v1 indexes real columns only — title, description, status, resource_type,
sectors, geographies, owner and dates. The author / date / usage-rights columns
and block content are intentionally NOT indexed (see the plan's Limitations).
``related_models`` is stated explicitly (not cloned blind) so that renaming a
Resource Type, sector or geography re-indexes the affected publications.
"""

from typing import Any, Dict, List, Optional, Union

from django_elasticsearch_dsl import Document, Index, KeywordField, fields

from api.models.Geography import Geography
from api.models.Organization import Organization
from api.models.Publication import Publication
from api.models.ResourceType import ResourceType
from api.models.Sector import Sector
from api.utils.enums import PublicationStatus
from authorization.models import User
from DataSpace import settings
from search.documents.analysers import html_strip, ngram_analyser

INDEX = Index(settings.ELASTICSEARCH_INDEX_NAMES[__name__])
INDEX.settings(number_of_shards=1, number_of_replicas=0)


@INDEX.doc_type
class PublicationDocument(Document):
    """Elasticsearch document for a published Resource."""

    title = fields.TextField(
        analyzer=ngram_analyser,
        fields={"raw": KeywordField(multi=False)},
    )
    description = fields.TextField(
        analyzer=html_strip,
        fields={"raw": fields.TextField(analyzer="keyword")},
    )
    status = fields.KeywordField()

    # Resource Type facet (name).
    resource_type = fields.TextField(
        attr="resource_type_indexing",
        analyzer=ngram_analyser,
        fields={"raw": KeywordField(multi=False)},
    )

    # Sectors facet (ManyToMany).
    sectors = fields.TextField(
        attr="sectors_indexing",
        analyzer=ngram_analyser,
        fields={
            "raw": fields.KeywordField(multi=True),
            "suggest": fields.CompletionField(multi=True),
        },
        multi=True,
    )

    # Geographies facet (ManyToMany).
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

    def prepare_organization(self, instance: Publication) -> Optional[Dict[str, str]]:
        """Prepare the owning organization for indexing."""
        if instance.organization:
            org = instance.organization
            return {"name": org.name, "logo": org.logo.url if org.logo else ""}
        return None

    def prepare_user(self, instance: Publication) -> Optional[Dict[str, str]]:
        """Prepare the owning user for indexing."""
        if instance.user:
            user = instance.user
            return {
                "name": user.full_name,
                "bio": user.bio or "",
                "profile_picture": (user.profile_picture.url if user.profile_picture else ""),
            }
        return None

    def should_index_object(self, obj: Any) -> bool:
        """Only PUBLISHED resources are indexed — drafts never reach search."""
        return bool(obj.status == PublicationStatus.PUBLISHED.value)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Index a published resource, or drop it from the index otherwise."""
        if self.should_index_object(self.to_dict()):  # type: ignore
            super().save(*args, **kwargs)
        else:
            self.delete(ignore=404)

    def get_queryset(self) -> Any:
        """Only published resources are populated into the index."""
        return (
            super(PublicationDocument, self)
            .get_queryset()
            .filter(status=PublicationStatus.PUBLISHED)
        )

    def get_instances_from_related(
        self,
        related_instance: Union[Organization, User, ResourceType, Sector, Geography],
    ) -> Optional[List[Publication]]:
        """Re-index the publications affected when a related row changes.

        Covers a renamed Resource Type / sector / geography and an updated owner
        so already-indexed facets don't go stale.
        """
        if isinstance(related_instance, Organization):
            return list(related_instance.publications.all())
        if isinstance(related_instance, User):
            return list(related_instance.publications.all())
        if isinstance(related_instance, ResourceType):
            return list(related_instance.publications.all())
        if isinstance(related_instance, Sector):
            return list(related_instance.publications.all())
        if isinstance(related_instance, Geography):
            return list(related_instance.publications.all())
        return None

    class Django:
        """Django model configuration."""

        model = Publication

        fields = [
            "id",
            "created",
            "modified",
        ]

        related_models = [Organization, User, ResourceType, Sector, Geography]
