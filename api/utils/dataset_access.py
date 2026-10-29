"""Who may see or change a dataset and the things hanging off it.

Resources, charts, chart images and access models have no rights of their own:
anyone who may change the dataset may change them, and they are visible to
whoever may see the dataset. The organisation is always the dataset's own;
nothing here reads the request's organisation header.
"""

from typing import Any, Optional

import structlog
from django.db.models import Q
from strawberry.permission import BasePermission
from strawberry.types import Info

from api.models import Dataset
from api.utils.enums import DatasetStatus
from authorization.models import DatasetPermission, OrganizationMembership

logger = structlog.get_logger(__name__)

# Organisation roles that may edit the organisation's datasets, by name.
DATASET_EDITOR_ROLE_NAMES = ["admin", "editor", "owner"]


def can_change_dataset(user: Any, dataset: Dataset) -> bool:
    """The one dataset edit rule, also used by UpdateDatasetPermission."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or dataset.user_id == user.id:
        return True
    if (
        dataset.organization_id
        and OrganizationMembership.objects.filter(
            user=user,
            organization_id=dataset.organization_id,
            role__name__in=DATASET_EDITOR_ROLE_NAMES,
        ).exists()
    ):
        return True
    dataset_perm = (
        DatasetPermission.objects.filter(user=user, dataset=dataset).select_related("role").first()
    )
    return bool(
        dataset_perm
        and dataset_perm.role.can_change
        and dataset.status == DatasetStatus.DRAFT.value
    )


def can_view_dataset(user: Any, dataset: Dataset) -> bool:
    """Published datasets are public; otherwise any one grant is enough."""
    if dataset.status == DatasetStatus.PUBLISHED.value:
        return True
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or dataset.user_id == user.id:
        return True
    if (
        dataset.organization_id
        and OrganizationMembership.objects.filter(
            user=user, organization_id=dataset.organization_id, role__can_view=True
        ).exists()
    ):
        return True
    if DatasetPermission.objects.filter(user=user, dataset=dataset, role__can_view=True).exists():
        return True
    return can_change_dataset(user, dataset)


def viewable_datasets_q(user: Any, prefix: str = "") -> Q:
    """`can_view_dataset` as a filter, for lists. `prefix` reaches the dataset, e.g. "dataset__"."""
    published = Q(**{f"{prefix}status": DatasetStatus.PUBLISHED.value})
    if not user or not user.is_authenticated:
        return published
    if user.is_superuser:
        return Q()
    orgs = OrganizationMembership.objects.filter(user=user).filter(
        Q(role__can_view=True) | Q(role__name__in=DATASET_EDITOR_ROLE_NAMES)
    )
    shared = DatasetPermission.objects.filter(user=user, role__can_view=True)
    draft_editors = DatasetPermission.objects.filter(
        user=user, role__can_change=True, dataset__status=DatasetStatus.DRAFT.value
    )
    return (
        published
        | Q(**{f"{prefix}user_id": user.id})
        | Q(**{f"{prefix}organization_id__in": orgs.values("organization_id")})
        | Q(**{f"{prefix}id__in": shared.values("dataset_id")})
        | Q(**{f"{prefix}id__in": draft_editors.values("dataset_id")})
    )


def can_list_organization(user: Any, organization: Any) -> bool:
    """Whether this user may list an organisation's datasets, drafts included."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return OrganizationMembership.objects.filter(
        user=user, organization=organization, role__can_view=True
    ).exists()


def log_access_denied(
    info: Info, user: Any, reason: str, dataset: Optional[Dataset] = None
) -> bool:
    """Record one warning for a refused request, and return False."""
    logger.warning(
        "dataset access denied",
        operation=info.field_name,
        user_id=getattr(user, "id", None),
        reason=reason,
        dataset_id=str(dataset.id) if dataset else None,
        organization_id=dataset.organization_id if dataset else None,
    )
    return False


class ChangeDatasetPartPermission(BasePermission):
    """Base for mutations on something that belongs to a dataset.

    Subclasses return every dataset the call touches (the one the object is in
    now and, when it is being moved, the one it goes to); the user needs edit
    rights on all of them. A missing ID is refused the same way, so the answer
    does not reveal whether an ID exists.
    """

    message = "You don't have permission to change this dataset"

    def datasets(self, kwargs: Any) -> Optional[list]:
        """The datasets the call touches, or None if any ID does not exist."""
        raise NotImplementedError

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        user = getattr(info.context, "user", None)
        if not user or not user.is_authenticated:
            return log_access_denied(info, user, "not_signed_in")
        datasets = self.datasets(kwargs)
        if not datasets:
            return log_access_denied(info, user, "target_not_found")
        for dataset in datasets:
            if not can_change_dataset(user, dataset):
                return log_access_denied(info, user, "not_allowed", dataset)
        return True
