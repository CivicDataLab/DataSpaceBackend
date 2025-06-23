from typing import Any, Dict, Optional

from django.http import HttpRequest

from api.activities.base import track_model_activity
from api.models.Organization import Organization
from authorization.models import User


def track_organization_created(
    user: User, organization: Organization, request: Optional[HttpRequest] = None
) -> None:
    """
    Track when an organization is created.
    """
    track_model_activity(
        actor=user,
        verb="created",
        model_instance=organization,
        request=request,
        extra_data={
            "organization_name": organization.name,
            "organization_id": str(organization.id),
            "organization_type": organization.organization_types,
        },
    )


def track_organization_updated(
    user: User,
    organization: Organization,
    updated_fields: Optional[Dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when an organization is updated.

    Args:
        user: The user performing the update
        organization: The organization being updated
        updated_fields: Dictionary of fields that were updated
        request: The current HTTP request
    """
    track_model_activity(
        actor=user,
        verb="updated",
        model_instance=organization,
        request=request,
        extra_data={
            "organization_name": organization.name,
            "organization_id": str(organization.id),
            "updated_fields": updated_fields or {},
        },
    )


def track_member_added(
    user: User,
    organization: Organization,
    member: User,
    role: str,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a member is added to an organization.

    Args:
        user: The user performing the action (adding the member)
        organization: The organization the member is being added to
        member: The user being added as a member
        role: The role assigned to the member
        request: The current HTTP request
    """
    track_model_activity(
        actor=user,
        verb="added member",
        model_instance=organization,
        target=member,  # The member being added is the target
        request=request,
        extra_data={
            "organization_name": organization.name,
            "organization_id": str(organization.id),
            "member_username": member.username,
            "member_id": str(member.id),
            "role": role,
        },
    )


def track_member_removed(
    user: User,
    organization: Organization,
    member: User,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a member is removed from an organization.
    """
    track_model_activity(
        actor=user,
        verb="removed member",
        model_instance=organization,
        target=member,  # The member being removed is the target
        request=request,
        extra_data={
            "organization_name": organization.name,
            "organization_id": str(organization.id),
            "member_username": member.username,
            "member_id": str(member.id),
        },
    )


def track_member_role_changed(
    user: User,
    organization: Organization,
    member: User,
    new_role: str,
    request: Optional[HttpRequest] = None,
) -> None:
    """
    Track when a member's role is changed in an organization.
    """
    track_model_activity(
        actor=user,
        verb="changed member role",
        model_instance=organization,
        target=member,  # The member whose role is being changed is the target
        request=request,
        extra_data={
            "organization_name": organization.name,
            "organization_id": str(organization.id),
            "member_username": member.username,
            "member_id": str(member.id),
            "new_role": new_role,
        },
    )
