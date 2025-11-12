"""DataSpace Python SDK for programmatic access to DataSpace resources."""

from dataspace_sdk.client import DataSpaceClient
from dataspace_sdk.exceptions import (
    DataSpaceAPIError,
    DataSpaceAuthError,
    DataSpaceNotFoundError,
    DataSpaceValidationError,
)

__version__ = "0.1.0"
__all__ = [
    "DataSpaceClient",
    "DataSpaceAPIError",
    "DataSpaceAuthError",
    "DataSpaceNotFoundError",
    "DataSpaceValidationError",
]
