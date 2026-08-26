from typing import Any, Optional, Union, cast

from django.db.models import Q
from rest_framework import permissions
from strawberry.permission import BasePermission
from strawberry.types import Info

from api.models import Dataset, Organization, Publication
from api.utils.enums import PublicationStatus
from authorization.models import DatasetPermission, OrganizationMembership, Role

# Roles that may publish/unpublish and edit an org-owned publication, by name.
PUBLICATION_MANAGER_ROLE_NAMES = ["admin", "editor", "owner"]


# REST Framework Permissions
class IsOrganizationMember(permissions.BasePermission):
    """
    Permission class to check if a user is a member of the organization
    that owns the object being accessed.
    """

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # Get the organization from the object
        organization = self._get_organization(obj)
        if not organization:
            return False

        # Check if the user is a member of the organization
        return OrganizationMembership.objects.filter(
            user=request.user, organization=organization
        ).exists()

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        """
        Get the organization from the object.
        Override this method in subclasses for specific object types.
        """
        if hasattr(obj, "organization"):
            return obj.organization  # type: ignore[attr-defined,no-any-return]
        return None


class HasOrganizationRole(permissions.BasePermission):
    """
    Permission class to check if a user has a specific role in the organization
    that owns the object being accessed.
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        # For list views, check if user has access to any organization
        if request.user.is_superuser:
            return True

        # For organization-specific endpoints
        org_id = request.query_params.get("organization") or request.data.get("organization")
        if org_id:
            return OrganizationMembership.objects.filter(
                user=request.user, organization_id=org_id
            ).exists()  # type: ignore[no-any-return]

        # For general list views, allow if user belongs to any organization
        return OrganizationMembership.objects.filter(user=request.user).exists()

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # Get the organization from the object
        organization = self._get_organization(obj)
        if not organization:
            return False

        # Get the user's role in the organization
        try:
            membership = OrganizationMembership.objects.get(
                user=request.user, organization=organization
            )
            role = membership.role  # type: ignore[attr-defined]

            # Map the HTTP method to an action
            method = request.method.lower()
            action = self._get_action_from_method(method)

            # Check if the user's role allows the action
            if action == "view":
                return role.can_view  # type: ignore[attr-defined]
            elif action == "add":
                return role.can_add  # type: ignore[attr-defined]
            elif action == "change":
                return role.can_change  # type: ignore[attr-defined]
            elif action == "delete":
                return role.can_delete  # type: ignore[attr-defined]
            return False

        except OrganizationMembership.DoesNotExist:
            return False

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        """
        Get the organization from the object.
        Override this method in subclasses for specific object types.
        """
        if hasattr(obj, "organization"):
            return obj.organization  # type: ignore[attr-defined,no-any-return]
        return None

    def _get_action_from_method(self, method: str) -> Optional[str]:
        """
        Map HTTP method to a permission action.
        """
        if method == "get":
            return "view"
        elif method == "post":
            return "add"
        elif method in ["put", "patch"]:
            return "change"
        elif method == "delete":
            return "delete"
        return None


# Strawberry GraphQL Permissions
class IsAuthenticated(BasePermission):
    """
    Permission class that checks if the user is authenticated.
    """

    message = "User is not authenticated"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context
        return request.user.is_authenticated  # type: ignore[no-any-return]


class IsOrganizationMemberGraphQL(BasePermission):  # type: ignore[misc]
    """
    Permission class to check if a user is a member of the organization
    that owns the object being accessed.
    """

    message = "User is not a member of the organization"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context

        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # For queries/mutations that don't have a source yet (e.g., creating a new object)
        if source is None:
            # Check if organization_id is provided in the arguments
            organization_id = kwargs.get("organization_id")
            if organization_id:
                return OrganizationMembership.objects.filter(
                    user=request.user, organization_id=organization_id
                ).exists()
            return True  # If no organization specified, allow and check later

        # For queries/mutations that have a source (e.g., updating an existing object)
        organization = self._get_organization(source)
        if not organization:
            return False

        return OrganizationMembership.objects.filter(
            user=request.user, organization=organization
        ).exists()

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        """
        Get the organization from the object.
        Override this method in subclasses for specific object types.
        """
        if hasattr(obj, "organization"):
            return obj.organization  # type: ignore[attr-defined,no-any-return]
        return None


class HasOrganizationRoleGraphQL(BasePermission):  # type: ignore[misc]
    """
    Permission class to check if a user has a specific role in the organization
    that owns the object being accessed.
    """

    message = "User does not have the required role in the organization"

    def __init__(self, operation: str = "view"):
        self.operation = operation

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context

        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # For queries/mutations that don't have a source yet (e.g., creating a new object)
        if source is None:
            # Check if organization_id is provided in the arguments
            organization_id = kwargs.get("organization_id")
            # Also check if organization is in the context
            organization = None
            if hasattr(info.context, "context") and isinstance(info.context.context, dict):
                organization = info.context.context.get("organization")

            if organization_id:
                try:
                    membership = OrganizationMembership.objects.get(
                        user=request.user, organization_id=organization_id
                    )
                    role = membership.role
                    return self._check_role_permission(role)  # type: ignore[no-any-return]
                except OrganizationMembership.DoesNotExist:
                    return False
            elif organization:
                try:
                    membership = OrganizationMembership.objects.get(
                        user=request.user, organization=organization
                    )
                    role = membership.role
                    return self._check_role_permission(role)  # type: ignore[no-any-return]
                except OrganizationMembership.DoesNotExist:
                    return False

            # If we're creating something that doesn't need organization permission yet,
            # we'll check later when the specific object is accessed
            return request.user.is_authenticated  # type: ignore[no-any-return]

        # For queries/mutations that have a source (e.g., updating an existing object)
        organization = self._get_organization(source)
        if not organization:
            return False

        try:
            membership = OrganizationMembership.objects.get(
                user=request.user, organization=organization
            )
            role = membership.role
            return self._check_role_permission(role)
        except OrganizationMembership.DoesNotExist:
            return False

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        """
        Get the organization from the object.
        Override this method in subclasses for specific object types.
        """
        if hasattr(obj, "organization"):
            return obj.organization  # type: ignore[attr-defined,no-any-return]
        return None

    def _check_role_permission(self, role: Role) -> bool:
        """
        Check if the role has the required permission for the operation.
        """
        if self.operation == "view":
            return role.can_view
        elif self.operation == "add":
            return role.can_add
        elif self.operation == "change":
            return role.can_change
        elif self.operation == "delete":
            return role.can_delete
        return False


# Specialized permission classes for specific models
class DatasetPermissionGraphQL(HasOrganizationRoleGraphQL):  # type: ignore[misc]
    """
    Permission class specifically for Dataset objects.
    Also checks for dataset-specific permissions and user ownership.
    """

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        # First check organization-level permissions
        if super().has_permission(source, info, **kwargs):
            return True

        # If not allowed at organization level, check dataset-specific permissions
        request = info.context

        # Check if user is authenticated before proceeding with permission checks
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return False

        # For queries/mutations that don't have a source yet
        if source is None:
            dataset_id = kwargs.get("dataset_id")
            if not dataset_id:
                return False
            try:
                # Check if the user owns this dataset
                dataset = Dataset.objects.get(id=dataset_id)
                if dataset.user and dataset.user == request.user:
                    return True

                # If not owned by user, check dataset-specific permissions
                dataset_perm = DatasetPermission.objects.get(
                    user=request.user, dataset_id=dataset_id
                )
                role = dataset_perm.role
                return self._check_role_permission(role)
            except (Dataset.DoesNotExist, DatasetPermission.DoesNotExist):
                return False

        # For queries/mutations that have a source
        if hasattr(source, "id"):
            # Check if the user owns this dataset
            if hasattr(source, "user") and source.user == request.user:
                return True

            try:
                dataset_perm = DatasetPermission.objects.get(user=request.user, dataset=source)
                role = dataset_perm.role
                return self._check_role_permission(role)
            except DatasetPermission.DoesNotExist:
                return False

        return False


class UserDatasetPermission(BasePermission):
    """
    Permission class that allows users to access their own datasets.
    """

    message = "You don't have permission to access this dataset"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context

        # Check if user is authenticated
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return False

        # For queries/mutations that don't have a source yet
        if source is None:
            dataset_id = kwargs.get("dataset_id")
            if dataset_id:
                try:
                    dataset = Dataset.objects.get(id=dataset_id)
                    # Allow access if user owns the dataset
                    return bool(dataset.user == request.user)
                except Dataset.DoesNotExist:
                    pass  # Let the resolver handle the non-existent dataset
            return False

        # For queries/mutations that have a source
        if hasattr(source, "user"):
            # Allow access if user owns the dataset
            return bool(source.user == request.user)

        return False


class CreateDatasetPermission(BasePermission):
    """
    Permission class for dataset creation.
    Allows users to create datasets either as part of an organization (if they have the right role)
    or as individual users.
    """

    message = "You don't have permission to create a dataset"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context

        # Check if user is authenticated - basic requirement for all dataset creation
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return False

        # If creating in organization context, check organization permissions
        organization = info.context.context.get("organization")
        if organization:
            try:
                # Check if user has the 'add' permission in the organization
                membership = OrganizationMembership.objects.get(
                    user=request.user, organization=organization
                )
                role = membership.role
                return role.can_add
            except OrganizationMembership.DoesNotExist:
                return False

        # If not in organization context, any authenticated user can create their own dataset
        return True


class ResourcePermissionGraphQL(HasOrganizationRoleGraphQL):  # type: ignore[misc]
    """
    Permission class specifically for Resource objects.
    """

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        return obj.dataset.organization if hasattr(obj, "dataset") else None  # type: ignore[attr-defined,no-any-return]


class PublishDatasetPermission(BasePermission):
    """Permission class for publishing a dataset.
    Checks if the user has permission to publish the dataset.
    """

    message = "You don't have permission to publish/unpublish this dataset"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context

        # Check if user is authenticated
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return False

        # Superusers have access to everything
        if request.user.is_superuser:
            return True

        # Get the dataset ID from the arguments
        dataset_id = kwargs.get("dataset_id")
        if not dataset_id:
            return False

        try:
            dataset = Dataset.objects.get(id=dataset_id)

            # Check if user owns the dataset
            if dataset.user and dataset.user == request.user:
                return True

            # If organization-owned, check organization permissions
            if dataset.organization:
                # Get the roles with names 'admin', 'editor', or 'owner'
                admin_editor_roles = Role.objects.filter(
                    name__in=["admin", "editor", "owner"]
                ).values_list("id", flat=True)

                # Check if user is a member of the dataset's organization with appropriate role
                org_member = OrganizationMembership.objects.filter(
                    user=request.user,
                    organization=dataset.organization,
                    role__id__in=admin_editor_roles,
                ).exists()

                if org_member:
                    return True

            # Check dataset-specific permissions
            dataset_perm = DatasetPermission.objects.filter(
                user=request.user, dataset=dataset
            ).first()
            return bool(dataset_perm and dataset_perm.role.can_change)

        except Dataset.DoesNotExist:
            return False


# ---------------------------------------------------------------------------
# Publication (UI "Resource") permissions
#
# Mirrors Dataset's dedicated permission classes rather than AIModel's inline
# per-resolver role checks. Publication has no per-object share model, so the
# share-model fallback is dropped; the individual-owner branch is kept so an
# org-less publication's owner isn't denied.
# ---------------------------------------------------------------------------


def _resolve_publication_id(kwargs: Any) -> Optional[Any]:
    """Pull the target publication's id out of a mutation's arguments.

    Publish/unpublish/delete pass ``publication_id`` directly; update passes an
    input object carrying the id on ``.id``.
    """
    publication_id = kwargs.get("publication_id")
    if publication_id:
        return publication_id
    for input_key in ("input", "update_input"):
        payload = kwargs.get(input_key)
        if payload is not None and getattr(payload, "id", None):
            return payload.id
    # Block-scoped mutations pass a block id — resolve to its parent publication.
    block_id = kwargs.get("block_id")
    if block_id:
        from api.models import PublicationBlock

        block = PublicationBlock.objects.filter(id=block_id).first()
        if block:
            return block.publication_id
    return None


def _user_manages_publication(user: Any, publication: Publication, operation: str) -> bool:
    """Whether a user may perform ``operation`` on a publication.

    Owner (individual publications) always may; for org-owned publications the
    caller must be a member whose role grants the operation (``publish`` and
    ``change``/``delete`` map to the role's name / boolean flags).
    """
    if user.is_superuser:
        return True
    if publication.user and publication.user == user:
        return True
    if not publication.organization:
        return False

    membership = OrganizationMembership.objects.filter(
        user=user, organization=publication.organization
    ).first()
    if not membership:
        return False

    role = membership.role
    if operation == "publish":
        return role.name in PUBLICATION_MANAGER_ROLE_NAMES
    if operation == "delete":
        return role.can_delete
    return role.can_change


class PublicationPermissionGraphQL(BasePermission):  # type: ignore[misc]
    """Base publication mutation permission — keys on the publication id in kwargs."""

    message = "You don't have permission to modify this resource"
    operation = "change"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        user = info.context.user
        if not getattr(user, "is_authenticated", False):
            return False

        publication_id = _resolve_publication_id(kwargs)
        if not publication_id:
            return False

        try:
            publication = Publication.objects.get(id=publication_id)
        except Publication.DoesNotExist:
            return False

        return _user_manages_publication(user, publication, self.operation)


class ChangePublicationPermission(PublicationPermissionGraphQL):
    operation = "change"


class DeletePublicationPermission(PublicationPermissionGraphQL):
    message = "You don't have permission to delete this resource"
    operation = "delete"


class PublishPublicationPermission(PublicationPermissionGraphQL):
    message = "You don't have permission to publish this resource"
    operation = "publish"


class CreatePublicationPermission(BasePermission):  # type: ignore[misc]
    """Permission for creating a publication — mirrors CreateDatasetPermission.

    Any authenticated user may create an individual publication; creating inside
    an organization context requires the ``add`` role in that organization.
    """

    message = "You don't have permission to create a resource"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        user = info.context.user
        if not getattr(user, "is_authenticated", False):
            return False

        organization = info.context.context.get("organization")
        if organization:
            membership = OrganizationMembership.objects.filter(
                user=user, organization=organization
            ).first()
            return bool(membership and membership.role.can_add)

        return True


class AllowPublishedPublications(BasePermission):  # type: ignore[misc]
    """Read gate for a single publication — mirrors AllowPublishedDatasets.

    A PUBLISHED publication is world-readable; a DRAFT is visible only to the
    owner, org members with view access, or a superuser.
    """

    message = "You need to be authenticated to access non-published resources"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context
        publication_id = kwargs.get("publication_id")

        if publication_id:
            try:
                publication = Publication.objects.get(id=publication_id)
            except Publication.DoesNotExist:
                return True  # Let the resolver return a clean not-found.

            if publication.status == PublicationStatus.PUBLISHED.value:
                return True

            user = request.user
            if not user.is_authenticated:
                return False
            if user.is_superuser:
                return True
            if publication.user and publication.user == user:
                return True
            if publication.organization:
                membership = OrganizationMembership.objects.filter(
                    user=user, organization=publication.organization
                ).first()
                return bool(membership and membership.role.can_view)
            return False

        # No id in kwargs (e.g. object source) — published is public, else auth.
        if hasattr(source, "status"):
            if source.status == PublicationStatus.PUBLISHED.value:
                return True
        return bool(getattr(request, "user", None) and request.user.is_authenticated)
