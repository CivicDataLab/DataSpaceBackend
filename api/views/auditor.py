"""REST API views for auditor management."""

import logging
from typing import Any, Dict, List, Optional

from django.db import transaction
from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.models import Organization
from authorization.models import OrganizationMembership, Role, User

logger = logging.getLogger(__name__)


class OrganizationAuditorsView(views.APIView):
    """
    View for managing auditors in an organization.

    GET: List all auditors for an organization
    POST: Add a user as auditor to an organization (by user_id or email)
    DELETE: Remove an auditor from an organization
    """

    permission_classes = [IsAuthenticated]

    def _get_organization(self, organization_id: str) -> Optional[Organization]:
        """Get organization by ID."""
        try:
            return Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            return None

    def _check_admin_permission(self, user: User, organization: Organization) -> bool:
        """Check if user has admin permission for the organization."""
        if user.is_superuser:
            return True
        try:
            membership = OrganizationMembership.objects.get(user=user, organization=organization)
            # Admin role has can_change permission
            return membership.role.can_change  # type: ignore[return-value]
        except OrganizationMembership.DoesNotExist:
            return False

    def _get_auditor_role(self) -> Optional[Role]:
        """Get the auditor role."""
        try:
            return Role.objects.get(name="auditor")
        except Role.DoesNotExist:
            logger.error("Auditor role not found. Please run migrations.")
            return None

    def get(self, request: Request, organization_id: str) -> Response:
        """Get all auditors for an organization."""
        organization = self._get_organization(organization_id)
        if not organization:
            return Response(
                {"error": f"Organization with ID {organization_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user has permission to view organization members
        if not self._check_admin_permission(request.user, organization):  # type: ignore[arg-type]
            return Response(
                {"error": "You don't have permission to view auditors for this organization"},
                status=status.HTTP_403_FORBIDDEN,
            )

        auditor_role = self._get_auditor_role()
        if not auditor_role:
            return Response(
                {"error": "Auditor role not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Get all auditors for this organization
        auditor_memberships = OrganizationMembership.objects.filter(
            organization=organization, role=auditor_role
        ).select_related("user")

        auditors: List[Dict[str, Any]] = []
        for membership in auditor_memberships:  # type: OrganizationMembership
            user: User = membership.user  # type: ignore[assignment]
            auditors.append(
                {
                    "id": str(user.id),
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "profile_picture": user.profile_picture.url if user.profile_picture else None,
                    "joined_at": (
                        membership.created_at.isoformat() if membership.created_at else None
                    ),
                }
            )

        return Response(
            {
                "organization_id": str(organization.id),
                "organization_name": organization.name,
                "auditors": auditors,
                "count": len(auditors),
            }
        )

    @transaction.atomic
    def post(self, request: Request, organization_id: str) -> Response:
        """
        Add a user as auditor to an organization.

        Request body can contain either:
        - user_id: ID of an existing user
        - email: Email of a user to add (will look up user by email)
        """
        organization = self._get_organization(organization_id)
        if not organization:
            return Response(
                {"error": f"Organization with ID {organization_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user has admin permission
        if not self._check_admin_permission(request.user, organization):  # type: ignore[arg-type]
            return Response(
                {"error": "You don't have permission to add auditors to this organization"},
                status=status.HTTP_403_FORBIDDEN,
            )

        auditor_role = self._get_auditor_role()
        if not auditor_role:
            return Response(
                {"error": "Auditor role not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        user_id = request.data.get("user_id")
        email = request.data.get("email")

        if not user_id and not email:
            return Response(
                {"error": "Either user_id or email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find the user
        target_user: Optional[User] = None
        if user_id:
            try:
                target_user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": f"User with ID {user_id} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        elif email:
            try:
                target_user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response(
                    {
                        "error": f"User with email {email} not found. The user must have an account in CivicDataSpace first."
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        if not target_user:
            return Response(
                {"error": "Could not find user"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user is already a member of the organization
        existing_membership = OrganizationMembership.objects.filter(
            user=target_user, organization=organization
        ).first()

        if existing_membership:
            if existing_membership.role == auditor_role:
                return Response(
                    {"error": "User is already an auditor for this organization"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            else:
                # User has a different role, update to auditor
                # Note: This might not be desired behavior - you may want to keep existing role
                # For now, we'll add them as auditor (they can have multiple roles in future)
                return Response(
                    {"error": f"User is already a member of this organization with role '{existing_membership.role.name}'"},  # type: ignore[attr-defined]
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Create the membership
        membership = OrganizationMembership.objects.create(
            user=target_user,
            organization=organization,
            role=auditor_role,
        )

        logger.info(
            f"Added user {target_user.username} as auditor to organization {organization.name}"
        )

        return Response(
            {
                "success": True,
                "message": f"User {target_user.username} added as auditor",
                "auditor": {
                    "id": target_user.id,
                    "username": target_user.username,
                    "email": target_user.email,
                    "first_name": target_user.first_name,
                    "last_name": target_user.last_name,
                    "joined_at": membership.created_at.isoformat(),
                },
            },
            status=status.HTTP_201_CREATED,
        )

    @transaction.atomic
    def delete(self, request: Request, organization_id: str) -> Response:
        """Remove an auditor from an organization."""
        organization = self._get_organization(organization_id)
        if not organization:
            return Response(
                {"error": f"Organization with ID {organization_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user has admin permission
        if not self._check_admin_permission(request.user, organization):  # type: ignore[arg-type]
            return Response(
                {"error": "You don't have permission to remove auditors from this organization"},
                status=status.HTTP_403_FORBIDDEN,
            )

        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"error": "user_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        auditor_role = self._get_auditor_role()
        if not auditor_role:
            return Response(
                {"error": "Auditor role not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            membership = OrganizationMembership.objects.get(
                user_id=user_id, organization=organization, role=auditor_role
            )
            username = membership.user.username  # type: ignore[attr-defined]
            membership.delete()

            logger.info(f"Removed auditor {username} from organization {organization.name}")

            return Response(
                {
                    "success": True,
                    "message": f"Auditor {username} removed from organization",
                }
            )
        except OrganizationMembership.DoesNotExist:
            return Response(
                {"error": "User is not an auditor for this organization"},
                status=status.HTTP_404_NOT_FOUND,
            )


class SearchUserByEmailView(views.APIView):
    """
    Search for a user by email.
    Used to find users before adding them as auditors.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Search for a user by email."""
        email = request.query_params.get("email")
        if not email:
            return Response(
                {"error": "email query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
            return Response(
                {
                    "found": True,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "profile_picture": (
                            user.profile_picture.url if user.profile_picture else None
                        ),
                    },
                }
            )
        except User.DoesNotExist:
            return Response(
                {
                    "found": False,
                    "message": f"No user found with email {email}",
                }
            )
