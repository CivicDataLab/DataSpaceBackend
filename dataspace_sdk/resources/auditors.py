"""Auditor management resource for DataSpace SDK."""

from typing import Any, Dict, Optional

import requests

from dataspace_sdk.exceptions import DataSpaceAuthError


class AuditorClient:
    """
    Client for managing auditors in organizations.

    Auditors are users with the 'auditor' role in an organization,
    who can audit AI models registered by that organization.
    """

    def __init__(self, base_url: str, auth_client: Any):
        """
        Initialize the auditor client.

        Args:
            base_url: Base URL of the DataSpace API
            auth_client: Authentication client instance
        """
        self._base_url = base_url.rstrip("/")
        self._auth = auth_client

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {"Content-Type": "application/json"}
        if self._auth and self._auth.access_token:
            headers["Authorization"] = f"Bearer {self._auth.access_token}"
        return headers

    def get_organization_auditors(self, organization_id: str) -> Dict[str, Any]:
        """
        Get all auditors for an organization.

        Args:
            organization_id: UUID of the organization

        Returns:
            Dictionary containing:
            - organization_id: str
            - organization_name: str
            - auditors: List of auditor dictionaries
            - count: int

        Raises:
            DataSpaceAuthError: If not authenticated or permission denied

        Example:
            >>> result = client.auditors.get_organization_auditors("org-uuid")
            >>> for auditor in result["auditors"]:
            ...     print(f"{auditor['username']} - {auditor['email']}")
        """
        self._auth.ensure_authenticated()

        url = f"{self._base_url}/api/organizations/{organization_id}/auditors/"

        response = requests.get(
            url,
            headers=self._get_headers(),
        )

        if response.status_code == 200:
            result: Dict[str, Any] = response.json()
            return result
        elif response.status_code == 401:
            raise DataSpaceAuthError("Authentication required")
        elif response.status_code == 403:
            raise DataSpaceAuthError("Permission denied: You must be an admin of this organization")
        elif response.status_code == 404:
            raise DataSpaceAuthError(f"Organization {organization_id} not found")
        else:
            error_data: Dict[str, Any] = response.json()
            raise DataSpaceAuthError(
                error_data.get("error", "Failed to get auditors"),
                status_code=response.status_code,
                response=error_data,
            )

    def add_auditor(
        self,
        organization_id: str,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a user as auditor to an organization.

        You must provide either user_id or email. If the user is found,
        they will be added as an auditor to the organization.

        Args:
            organization_id: UUID of the organization
            user_id: Optional user ID to add as auditor
            email: Optional email to look up user and add as auditor

        Returns:
            Dictionary containing:
            - success: bool
            - message: str
            - auditor: Dictionary with auditor details

        Raises:
            DataSpaceAuthError: If not authenticated, permission denied, or user not found
            ValueError: If neither user_id nor email is provided

        Example:
            >>> # Add by user ID
            >>> result = client.auditors.add_auditor("org-uuid", user_id="user-uuid")
            >>>
            >>> # Add by email
            >>> result = client.auditors.add_auditor("org-uuid", email="auditor@example.com")
        """
        if not user_id and not email:
            raise ValueError("Either user_id or email must be provided")

        self._auth.ensure_authenticated()

        url = f"{self._base_url}/api/organizations/{organization_id}/auditors/"

        payload: Dict[str, str] = {}
        if user_id:
            payload["user_id"] = user_id
        if email:
            payload["email"] = email

        response = requests.post(
            url,
            json=payload,
            headers=self._get_headers(),
        )

        if response.status_code == 201:
            result: Dict[str, Any] = response.json()
            return result
        elif response.status_code == 401:
            raise DataSpaceAuthError("Authentication required")
        elif response.status_code == 403:
            raise DataSpaceAuthError("Permission denied: You must be an admin of this organization")
        elif response.status_code == 404:
            error_data = response.json()
            raise DataSpaceAuthError(
                error_data.get("error", "Organization or user not found"),
                status_code=response.status_code,
                response=error_data,
            )
        elif response.status_code == 400:
            error_data = response.json()
            raise DataSpaceAuthError(
                error_data.get("error", "Invalid request"),
                status_code=response.status_code,
                response=error_data,
            )
        else:
            error_data = response.json()
            raise DataSpaceAuthError(
                error_data.get("error", "Failed to add auditor"),
                status_code=response.status_code,
                response=error_data,
            )

    def remove_auditor(self, organization_id: str, user_id: str) -> Dict[str, Any]:
        """
        Remove an auditor from an organization.

        Args:
            organization_id: UUID of the organization
            user_id: ID of the user to remove as auditor

        Returns:
            Dictionary containing:
            - success: bool
            - message: str

        Raises:
            DataSpaceAuthError: If not authenticated, permission denied, or user not an auditor

        Example:
            >>> result = client.auditors.remove_auditor("org-uuid", "user-uuid")
            >>> print(result["message"])
        """
        self._auth.ensure_authenticated()

        url = f"{self._base_url}/api/organizations/{organization_id}/auditors/"

        response = requests.delete(
            url,
            json={"user_id": user_id},
            headers=self._get_headers(),
        )

        if response.status_code == 200:
            result: Dict[str, Any] = response.json()
            return result
        elif response.status_code == 401:
            raise DataSpaceAuthError("Authentication required")
        elif response.status_code == 403:
            raise DataSpaceAuthError("Permission denied: You must be an admin of this organization")
        elif response.status_code == 404:
            error_data: Dict[str, Any] = response.json()
            raise DataSpaceAuthError(
                error_data.get("error", "Organization or auditor not found"),
                status_code=response.status_code,
                response=error_data,
            )
        else:
            error_data_other: Dict[str, Any] = response.json()
            raise DataSpaceAuthError(
                error_data_other.get("error", "Failed to remove auditor"),
                status_code=response.status_code,
                response=error_data_other,
            )

    def search_user_by_email(self, email: str) -> Dict[str, Any]:
        """
        Search for a user by email address.

        This is useful to check if a user exists before adding them as an auditor.

        Args:
            email: Email address to search for

        Returns:
            Dictionary containing:
            - found: bool
            - user: Dictionary with user details (if found)
            - message: str (if not found)

        Raises:
            DataSpaceAuthError: If not authenticated

        Example:
            >>> result = client.auditors.search_user_by_email("user@example.com")
            >>> if result["found"]:
            ...     print(f"Found user: {result['user']['username']}")
            ... else:
            ...     print("User not found")
        """
        self._auth.ensure_authenticated()

        url = f"{self._base_url}/api/users/search-by-email/"

        response = requests.get(
            url,
            params={"email": email},
            headers=self._get_headers(),
        )

        if response.status_code == 200:
            result: Dict[str, Any] = response.json()
            return result
        elif response.status_code == 401:
            raise DataSpaceAuthError("Authentication required")
        else:
            error_data: Dict[str, Any] = response.json()
            raise DataSpaceAuthError(
                error_data.get("error", "Failed to search user"),
                status_code=response.status_code,
                response=error_data,
            )
