"""Who may see or change a dataset and the things hanging off it.

Resources, charts, chart images and access models have no rights of their own:
anyone who may change the dataset may change them, and they are visible to
whoever may see the dataset.
"""

from typing import Any, Optional

from django.db.models import Q
from strawberry.permission import BasePermission
from strawberry.types import Info

from api.models import Dataset
from api.utils.enums import DatasetStatus
from authorization.models import DatasetPermission, OrganizationMembership


def can_view_dataset(user: Any, dataset: Dataset) -> bool:
    """Published datasets are public; drafts only for people who may see them."""
    if dataset.status == DatasetStatus.PUBLISHED.value:
        return True
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or dataset.user_id == user.id:
        return True
    dataset_perm = (
        DatasetPermission.objects.filter(user=user, dataset=dataset).select_related("role").first()
    )
    if dataset_perm:
        return bool(dataset_perm.role.can_view)
    membership = (
        OrganizationMembership.objects.filter(user=user, organization_id=dataset.organization_id)
        .select_related("role")
        .first()
        if dataset.organization_id
        else None
    )
    return bool(membership and membership.role.can_view)


def viewable_datasets_q(user: Any, prefix: str = "") -> Q:
    """`can_view_dataset` as a filter, for lists. `prefix` reaches the dataset, e.g. "dataset__"."""
    published = Q(**{f"{prefix}status": DatasetStatus.PUBLISHED.value})
    if not user or not user.is_authenticated:
        return published
    if user.is_superuser:
        return Q()
    shared = DatasetPermission.objects.filter(user=user, role__can_view=True).values("dataset_id")
    refused = DatasetPermission.objects.filter(user=user, role__can_view=False).values("dataset_id")
    orgs = OrganizationMembership.objects.filter(user=user, role__can_view=True).values(
        "organization_id"
    )
    return (
        published
        | Q(**{f"{prefix}user_id": user.id})
        | Q(**{f"{prefix}id__in": shared})
        | (Q(**{f"{prefix}organization_id__in": orgs}) & ~Q(**{f"{prefix}id__in": refused}))
    )


def can_change_dataset(user: Any, dataset: Dataset) -> bool:
    """Same rules as UpdateDatasetPermission in dataset_schema."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or dataset.user_id == user.id:
        return True
    if (
        dataset.organization_id
        and OrganizationMembership.objects.filter(
            user=user,
            organization_id=dataset.organization_id,
            role__name__in=["admin", "editor", "owner"],
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
            return False
        datasets = self.datasets(kwargs)
        if not datasets:
            return False
        return all(can_change_dataset(user, d) for d in datasets)
