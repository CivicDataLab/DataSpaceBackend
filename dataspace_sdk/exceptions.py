"""Custom exceptions for DataSpace SDK."""

from typing import Any, Optional


class DataSpaceAPIError(Exception):
    """Base exception for DataSpace API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional[dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class DataSpaceAuthError(DataSpaceAPIError):
    """Exception raised for authentication errors."""

    pass


class DataSpaceNotFoundError(DataSpaceAPIError):
    """Exception raised when a resource is not found."""

    pass


class DataSpaceValidationError(DataSpaceAPIError):
    """Exception raised for validation errors."""

    pass
