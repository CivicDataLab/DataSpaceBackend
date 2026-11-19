"""Who may see or change a use case or collaborative.

Both are owned by a user and, optionally, an organisation, and are either DRAFT
or PUBLISHED. Everyone sees a published one. A draft is seen by its owner,
members of its organisation whose role can view, and superusers. Changing one
(edit, link, publish, unpublish) needs the owner, a superuser, or a member of
its organisation whose role can change; deleting needs a role that can delete.
"""

from typing import Any, Optional

from django.db.models import Q

from api.utils.enums import CollaborativeStatus, UseCaseStatus
from authorization.models import OrganizationMembership

PUBLISHED_STATUSES = {UseCaseStatus.PUBLISHED.value, CollaborativeStatus.PUBLISHED.value}

# Role flag each operation needs from a member of the item's organisation.
_ROLE_FLAG = {"view": "can_view", "change": "can_change", "delete": "can_delete"}


def _role_allows(user: Any, item: Any, operation: str) -> bool:
    if not item.organization_id:
        return False
    membership = (
        OrganizationMembership.objects.filter(user=user, organization_id=item.organization_id)
        .select_related("role")
        .first()
    )
    return bool(membership and membership.role and getattr(membership.role, _ROLE_FLAG[operation]))


def can_manage_item(user: Any, item: Any, operation: str = "change") -> bool:
    """Whether this user may ``change`` (incl. publish) or ``delete`` the item."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or item.user_id == user.id:
        return True
    return _role_allows(user, item, operation)


def can_view_item(user: Any, item: Any) -> bool:
    """Published items for everyone; drafts for owner, viewing org members, superusers."""
    if item.status in PUBLISHED_STATUSES:
        return True
    return can_manage_item(user, item, "view")


def find_by_id(model: Any, value: Any) -> Optional[Any]:
    """The row with this integer id, or None (also for a malformed id)."""
    if value in (None, ""):
        return None
    try:
        return model.objects.filter(id=value).first()
    except (TypeError, ValueError):
        return None


def find_visible(model: Any, value: Any, user: Any) -> Optional[Any]:
    """The item with this id if the user may see it; a hidden draft is None,
    the same as a missing id."""
    item = find_by_id(model, value)
    return item if item is not None and can_view_item(user, item) else None


def viewable_items_q(user: Any, prefix: str = "") -> Q:
    """`can_view_item` as a filter; ``prefix`` reaches the item through a relation."""
    published = Q(**{f"{prefix}status__in": PUBLISHED_STATUSES})
    if not user or not user.is_authenticated:
        return published
    if user.is_superuser:
        return Q()
    viewing_orgs = OrganizationMembership.objects.filter(user=user, role__can_view=True).values(
        "organization_id"
    )
    return (
        published
        | Q(**{f"{prefix}user": user})
        | Q(**{f"{prefix}organization_id__in": viewing_orgs})
    )
