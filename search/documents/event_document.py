"""Elasticsearch document for Event.

Indexes published events only: name, location, dates, link (``public_id`` /
``url_slug``), owner and ``cover_url``. The cover is looked up on Luma every
time the document is built (``prepare_cover_url``), including the deploy's
``search_index --populate``; it is display-only (not searchable). The Luma
embed itself is not indexed; the event page fetches it with ``eventBySlug``.
"""

from typing import Any, Dict, List, Optional, Union

from django_elasticsearch_dsl import Document, Index, KeywordField, fields

from api.models.Event import Event
from api.models.Organization import Organization
from api.utils.enums import EventStatus
from api.utils.luma_cover import fetch_luma_cover
from authorization.models import User
from DataSpace import settings
from search.documents.analysers import ngram_analyser, title_subfields

INDEX = Index(settings.ELASTICSEARCH_INDEX_NAMES[__name__])
INDEX.settings(number_of_shards=1, number_of_replicas=0)


@INDEX.doc_type
class EventDocument(Document):
    """Elasticsearch document for a published event."""

    name = fields.TextField(
        analyzer=ngram_analyser,
        fields=title_subfields(),
    )
    location = fields.TextField(
        analyzer=ngram_analyser,
        fields={"raw": KeywordField(multi=False)},
    )
    status = fields.KeywordField()
    public_id = fields.KeywordField()
    url_slug = fields.KeywordField(attr="url_slug")
    is_individual_event = fields.BooleanField(attr="is_individual_event")
    cover_url = fields.KeywordField(index=False)

    organization = fields.NestedField(
        properties={
            "name": fields.TextField(analyzer=ngram_analyser),
            "logo": fields.TextField(analyzer=ngram_analyser),
        }
    )
    user = fields.NestedField(
        properties={
            "name": fields.TextField(analyzer=ngram_analyser),
            "bio": fields.TextField(analyzer=ngram_analyser),
            "profile_picture": fields.TextField(analyzer=ngram_analyser),
        }
    )

    def prepare_location(self, instance: Event) -> Optional[str]:
        """Blank locations are left out, so they never show up as a filter option."""
        return instance.location or None

    def prepare_cover_url(self, instance: Event) -> Optional[str]:
        """Cover image from Luma for the stored embed; None when Luma has none or fails."""
        embed = instance.luma_embed if isinstance(instance.luma_embed, dict) else {}
        return fetch_luma_cover(embed.get("src"))

    def prepare_organization(self, instance: Event) -> Optional[Dict[str, str]]:
        """Prepare the owning organization for indexing."""
        if instance.organization:
            org = instance.organization
            return {"name": org.name, "logo": org.logo.url if org.logo else ""}
        return None

    def prepare_user(self, instance: Event) -> Optional[Dict[str, str]]:
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
        """Only PUBLISHED events are indexed — drafts never reach search."""
        return bool(obj.status == EventStatus.PUBLISHED.value)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Index a published event, or drop it from the index otherwise."""
        if self.should_index_object(self.to_dict()):  # type: ignore
            super().save(*args, **kwargs)
        else:
            self.delete(ignore=404)

    def get_queryset(self) -> Any:
        """Only published events are populated into the index."""
        return super(EventDocument, self).get_queryset().filter(status=EventStatus.PUBLISHED)

    def get_instances_from_related(
        self, related_instance: Union[Organization, User]
    ) -> Optional[List[Event]]:
        """Re-index an owner's events when the owner's name or picture changes."""
        if isinstance(related_instance, (Organization, User)):
            return list(related_instance.events.all())
        return None

    class Django:
        """Django model configuration."""

        model = Event

        fields = [
            "id",
            "start_date",
            "end_date",
            "created",
            "modified",
        ]

        related_models = [Organization, User]
