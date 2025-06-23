"""GraphQL types for authorization module."""

from typing import List, Optional, cast

import strawberry
from strawberry.permission import BasePermission
from strawberry.types import Info


@strawberry.type
class RoleType:
    id: strawberry.ID
    name: str
    description: Optional[str]
    can_view: bool
    can_add: bool
    can_change: bool
    can_delete: bool


@strawberry.type
class OrganizationPermissionType:
    organization_id: strawberry.ID
    organization_name: str
    role_name: str
    can_view: bool
    can_add: bool
    can_change: bool
    can_delete: bool


@strawberry.type
class DatasetPermissionType:
    dataset_id: strawberry.ID
    dataset_title: str
    role_name: str
    can_view: bool
    can_add: bool
    can_change: bool
    can_delete: bool


@strawberry.type
class UserPermissionsType:
    organizations: List[OrganizationPermissionType]
    datasets: List[DatasetPermissionType]


@strawberry.type
class SuccessResponse:
    """Response type for mutations that return success/failure status."""

    success: bool
    message: Optional[str] = None
