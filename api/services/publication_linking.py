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


def assert_can_manage_links(user: Any, owner_user: Any, organization: Any) -> None:
    """Raise unless the caller may edit this Use Case / Collaborative's links.

    Editing links changes the container, so it needs the container's own
    authorization: its owner, or an org member with the change role (superusers
    always). This is independent of the linked resource, so the intentional
    cross-org affordance — org B's use case linking org A's published resource —
    still works: the caller is authorized on *their own* use case.
    """
    if getattr(user, "is_superuser", False):
        return
    if not getattr(user, "is_authenticated", False):
        raise ValueError("Authentication required.")
    if owner_user and owner_user == user:
        return
    if organization:
        from authorization.models import OrganizationMembership

        membership = OrganizationMembership.objects.filter(
            user=user, organization=organization
        ).first()
        if membership and membership.role.can_change:
            return
    raise ValueError("You don't have permission to modify this.")
