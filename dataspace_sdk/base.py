"""Base client for making API requests."""

from typing import Any, Dict, Optional

import requests

from dataspace_sdk.exceptions import (
    DataSpaceAPIError,
    DataSpaceAuthError,
    DataSpaceNotFoundError,
    DataSpaceValidationError,
)


class BaseAPIClient:
    """Base client for making API requests to DataSpace."""

    def __init__(self, base_url: str, auth_client: Any = None):
        """
        Initialize the base API client.

        Args:
            base_url: Base URL of the DataSpace API
            auth_client: Authentication client instance
        """
        self.base_url = base_url.rstrip("/")
        self.auth_client = auth_client

    def _get_headers(self, additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Get request headers including authentication.

        Args:
            additional_headers: Additional headers to include

        Returns:
            Dictionary of headers
        """
        headers = {"Content-Type": "application/json"}

        if self.auth_client and self.auth_client.is_authenticated():
            headers["Authorization"] = f"Bearer {self.auth_client.access_token}"

        if additional_headers:
            headers.update(additional_headers)

        return headers

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            data: Form data
            json_data: JSON data
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            DataSpaceAPIError: For API errors
            DataSpaceAuthError: For authentication errors
            DataSpaceNotFoundError: For 404 errors
            DataSpaceValidationError: For validation errors
        """
        url = f"{self.base_url}{endpoint}"
        request_headers = self._get_headers(headers)

        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json_data,
                headers=request_headers,
            )

            # Handle different status codes
            if response.status_code == 200 or response.status_code == 201:
                result: Dict[str, Any] = response.json() if response.content else {}
                return result
            elif response.status_code == 204:
                return {}
            elif response.status_code == 401:
                raise DataSpaceAuthError(
                    "Authentication required or token expired",
                    status_code=response.status_code,
                    response=response.json() if response.content else {},
                )
            elif response.status_code == 404:
                raise DataSpaceNotFoundError(
                    "Resource not found",
                    status_code=response.status_code,
                    response=response.json() if response.content else {},
                )
            elif response.status_code == 400:
                raise DataSpaceValidationError(
                    "Validation error",
                    status_code=response.status_code,
                    response=response.json() if response.content else {},
                )
            else:
                raise DataSpaceAPIError(
                    f"API request failed with status {response.status_code}",
                    status_code=response.status_code,
                    response=response.json() if response.content else {},
                )

        except requests.RequestException as e:
            raise DataSpaceAPIError(f"Network error: {str(e)}")

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a GET request."""
        return self._make_request("GET", endpoint, params=params)

    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a POST request."""
        return self._make_request("POST", endpoint, data=data, json_data=json_data)

    def put(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a PUT request."""
        return self._make_request("PUT", endpoint, data=data, json_data=json_data)

    def patch(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a PATCH request."""
        return self._make_request("PATCH", endpoint, data=data, json_data=json_data)

    def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make a DELETE request."""
        response = self._make_request("DELETE", endpoint)
        result: Dict[str, Any] = response if isinstance(response, dict) else {}
        return result
