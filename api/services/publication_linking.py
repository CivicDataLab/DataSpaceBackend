"""
publication_linking
────────────────────
Helpers for pulling published Resources into Use Cases and Collaboratives.

Resources are the first non-Dataset entity that can be linked, and only a
PUBLISHED resource may be linked — like a public library. These guard the link
mutations and the published-only render filter so a draft can never sneak into a
Use Case / Collaborative, and an unpublished resource silently drops out of the
render.
"""

from typing import Any, List

from api.models import Publication
from api.utils.enums import PublicationStatus


def get_linkable_publication(publication_id: Any) -> Publication:
    """Load a resource that is allowed to be linked, or raise.

    Only a PUBLISHED resource is linkable; a missing or draft one raises a clean
    error so the plain link mutation never attaches a draft.
    """
    try:
        publication = Publication.objects.get(id=publication_id)
    except Publication.DoesNotExist:
        raise ValueError(f"Resource {publication_id} does not exist.")
    if publication.status != PublicationStatus.PUBLISHED.value:
        raise ValueError("Only a published resource can be linked.")
    return publication


def published_publications(publication_ids: List[Any]) -> List[Publication]:
    """Return the published resources among the given ids (drafts dropped)."""
    return list(
        Publication.objects.filter(id__in=publication_ids, status=PublicationStatus.PUBLISHED)
    )
