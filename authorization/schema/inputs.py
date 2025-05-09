"""Input types for authorization GraphQL schema."""

from typing import Optional

import strawberry
from strawberry.file_uploads import Upload


@strawberry.input
class UpdateUserInput:
    """Input for updating user details."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    profile_picture: Optional[Upload] = None
    email: Optional[str] = None


@strawberry.input
class AddUserToOrganizationInput:
    """Input for adding a user to an organization."""

    user_id: strawberry.ID
    role_id: strawberry.ID


@strawberry.input
class AssignOrganizationRoleInput:
    user_id: strawberry.ID
    role_name: str


@strawberry.input
class AssignDatasetPermissionInput:
    user_id: strawberry.ID
    dataset_id: strawberry.ID
    role_name: str
