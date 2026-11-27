"""Who may act inside an organisation chosen by the request's organisation header.

The header only says which organisation the caller is working in; the context
middleware checks that the organisation exists, not that the caller belongs to
it. Anything that lists or creates inside that organisation checks membership
here first.
"""

from typing import Any

from authorization.models import OrganizationMembership


def can_list_organization(user: Any, organization: Any) -> bool:
    """Whether this user may list an organisation's items, drafts included."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return OrganizationMembership.objects.filter(
        user=user, organization=organization, role__can_view=True
    ).exists()


def can_add_to_organization(user: Any, organization: Any) -> bool:
    """Whether this user may create items owned by an organisation."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return OrganizationMembership.objects.filter(
        user=user, organization=organization, role__can_add=True
    ).exists()
