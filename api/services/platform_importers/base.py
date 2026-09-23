"""Shared contract for third-party platform importers.

An importer turns a user-supplied identifier (short id or pasted URL) into a
normalised ``PlatformDatasetInfo`` by calling the platform's public API.
Importers fetch *metadata only* — title, description, license, tags, author,
last updated and the dataset's page URL. Files are never listed or copied.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
import structlog
from django.conf import settings
from django.utils.dateparse import parse_datetime

from api.utils.enums import DatasetLicense, ImportPlatform

logger = structlog.get_logger("dataspace.platform_import")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class PlatformImportError(Exception):
    """Base class for importer failures. ``message`` is safe to show to users."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidIdentifierError(PlatformImportError):
    """The identifier/URL does not look like anything the platform accepts."""


class PlatformDatasetNotFoundError(PlatformImportError):
    """The platform reported no dataset for this identifier."""


class PlatformAuthError(PlatformImportError):
    """Credentials are missing/invalid, or the dataset is private/gated."""


class PlatformUnavailableError(PlatformImportError):
    """Network failure, timeout, rate limit, or a 5xx from the platform."""


# --------------------------------------------------------------------------- #
# Normalised result
# --------------------------------------------------------------------------- #
@dataclass
class PlatformColumn:
    """One column of the dataset as the platform describes it."""

    name: str
    field_type: str  # a FieldTypes value: STRING / NUMBER / INTEGER / DATE / BOOLEAN


@dataclass
class PlatformDatasetInfo:
    """Everything an importer returns. Each field lands in a typed column on
    DatasetSource (or on Dataset / ResourceSchema); nothing raw is kept."""

    platform: str
    identifier: str
    title: str
    description: str  # short form, fits Dataset.description (1,000 chars)
    source_url: str
    author: str = ""
    license: str = ""
    tags: List[str] = field(default_factory=list)
    last_updated: Optional[datetime] = None
    created_at: Optional[datetime] = None
    revision: str = ""
    readme: str = ""  # full card / README, unbounded
    citation: str = ""
    languages: List[str] = field(default_factory=list)
    homepage: str = ""
    is_archived: bool = False
    columns: List[PlatformColumn] = field(default_factory=list)

    @property
    def mapped_license(self) -> str:
        return map_license(self.license)


# --------------------------------------------------------------------------- #
# Helpers shared by importers
# --------------------------------------------------------------------------- #
# Platform license strings (lower-cased) -> DatasetLicense. Anything not listed
# falls back to CC-BY 4.0 and the raw string is kept on DatasetSource.
LICENSE_ALIASES: Dict[str, str] = {
    "cc-by-4.0": DatasetLicense.CC_BY_4_0_ATTRIBUTION,
    "cc-by": DatasetLicense.CC_BY_4_0_ATTRIBUTION,
    "cc by 4.0": DatasetLicense.CC_BY_4_0_ATTRIBUTION,
    "attribution 4.0 international (cc by 4.0)": DatasetLicense.CC_BY_4_0_ATTRIBUTION,
    "cc-by-sa-4.0": DatasetLicense.CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE,
    "cc-by-sa": DatasetLicense.CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE,
    "attribution-sharealike 4.0 international (cc by-sa 4.0)": (
        DatasetLicense.CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE
    ),
    "odc-by": DatasetLicense.OPEN_DATA_COMMONS_BY_ATTRIBUTION,
    "odc-by-1.0": DatasetLicense.OPEN_DATA_COMMONS_BY_ATTRIBUTION,
    "odc attribution license (odc-by)": DatasetLicense.OPEN_DATA_COMMONS_BY_ATTRIBUTION,
    "odbl": DatasetLicense.OPEN_DATABASE_LICENSE,
    "odbl-1.0": DatasetLicense.OPEN_DATABASE_LICENSE,
    "odc-odbl": DatasetLicense.OPEN_DATABASE_LICENSE,
    "database: open database, contents: database contents": DatasetLicense.OPEN_DATABASE_LICENSE,
    "database: open database, contents: © original authors": DatasetLicense.OPEN_DATABASE_LICENSE,
}


def map_license(raw: str) -> str:
    """Map a platform license string onto DatasetLicense (default CC-BY-4.0)."""
    key = (raw or "").strip().lower()
    return LICENSE_ALIASES.get(key, DatasetLicense.CC_BY_4_0_ATTRIBUTION)


def field_type_for(dtype: Any) -> str:
    """Map a platform column type (Hugging Face / Arrow style names) onto FieldTypes."""
    name = str(dtype if isinstance(dtype, str) else "").lower()
    if name in ("bool", "boolean"):
        return "BOOLEAN"
    if name.startswith(("int", "uint")):
        return "INTEGER"
    if name.startswith(("float", "double", "decimal")):
        return "NUMBER"
    if name.startswith(("date", "timestamp", "time")):
        return "DATE"
    return "STRING"  # strings, class labels, nested/binary types


def shorten(text: str, limit: int = 1000) -> str:
    """Cut on a word boundary with an ellipsis; used for Dataset.description."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…"


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a platform timestamp. Django's parser copes with a trailing ``Z``
    and any number of fractional digits (Kaggle sends e.g. ``...:04.7Z``),
    which ``datetime.fromisoformat`` on Python 3.10 does not."""
    if not value:
        return None
    try:
        return parse_datetime(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Base importer
# --------------------------------------------------------------------------- #
class PlatformImporter(ABC):
    """Contract every platform importer implements."""

    platform: str
    #: Human name used in user-facing messages, e.g. "Hugging Face".
    label: str = ""
    #: Hostnames whose URLs this importer can parse (used by parse_identifier).
    hosts: tuple = ()

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.timeout: float = float(getattr(settings, "PLATFORM_IMPORT_TIMEOUT", 15))

    @abstractmethod
    def parse_identifier(self, value: str) -> str:
        """Normalise a short id or pasted URL to the platform's canonical id.

        Raises InvalidIdentifierError when it cannot.
        """

    @abstractmethod
    def fetch_dataset_info(self, identifier: str) -> PlatformDatasetInfo:
        """Call the platform API and return normalised metadata."""

    # -- HTTP plumbing ------------------------------------------------------- #
    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        """GET with uniform error mapping. Subclasses add auth via kwargs."""
        kwargs.setdefault("timeout", self.timeout)
        name = self.label or str(self.platform)
        try:
            response = self.session.get(url, **kwargs)
        except requests.Timeout as exc:
            raise PlatformUnavailableError(f"{name} timed out") from exc
        except requests.RequestException as exc:
            logger.warning(
                "platform_import_request_failed", platform=self.platform, url=url, error=str(exc)
            )
            raise PlatformUnavailableError(f"Could not reach {name}") from exc

        if response.status_code == 404:
            raise PlatformDatasetNotFoundError(f"Dataset not found on {name}")
        if response.status_code in (401, 403):
            raise PlatformAuthError(
                f"{name} refused access. The dataset may be private/gated, "
                "or the server credentials are missing or invalid."
            )
        if response.status_code == 429:
            raise PlatformUnavailableError(f"{name} rate limit reached, try again later")
        if response.status_code >= 500:
            raise PlatformUnavailableError(f"{name} returned an error ({response.status_code})")
        if response.status_code >= 400:
            raise PlatformImportError(f"{name} rejected the request ({response.status_code})")
        return response

    def _get_json(self, url: str, **kwargs: Any) -> Any:
        response = self._get(url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise PlatformUnavailableError(
                f"{self.label or self.platform} returned an unreadable response"
            ) from exc


__all__ = [
    "ImportPlatform",
    "PlatformImporter",
    "PlatformDatasetInfo",
    "PlatformColumn",
    "PlatformImportError",
    "InvalidIdentifierError",
    "PlatformDatasetNotFoundError",
    "PlatformAuthError",
    "PlatformUnavailableError",
    "map_license",
    "field_type_for",
    "shorten",
    "parse_iso_datetime",
]
