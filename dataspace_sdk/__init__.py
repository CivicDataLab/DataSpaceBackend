"""DataSpace Python SDK for programmatic access to DataSpace resources."""

from dataspace_sdk.__version__ import __version__
from dataspace_sdk.client import DataSpaceClient
from dataspace_sdk.exceptions import (
    DataSpaceAPIError,
    DataSpaceAuthError,
    DataSpaceNotFoundError,
    DataSpaceValidationError,
)

__all__ = [
    "DataSpaceClient",
    "DataSpaceAPIError",
    "DataSpaceAuthError",
    "DataSpaceNotFoundError",
    "DataSpaceValidationError",
]
