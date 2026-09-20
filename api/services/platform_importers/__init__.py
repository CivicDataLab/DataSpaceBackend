"""Registry of third-party platform importers.

Add a platform by subclassing ``PlatformImporter`` and registering it here;
the GraphQL layer and import service never reference a concrete importer.
"""

from typing import Dict, Optional, Type
from urllib.parse import urlparse

from api.services.platform_importers.base import (
    InvalidIdentifierError,
    PlatformAuthError,
    PlatformDatasetInfo,
    PlatformDatasetNotFoundError,
    PlatformImporter,
    PlatformImportError,
    PlatformUnavailableError,
)
from api.services.platform_importers.github import GitHubImporter
from api.services.platform_importers.huggingface import HuggingFaceImporter
from api.services.platform_importers.kaggle import KaggleImporter
from api.utils.enums import ImportPlatform

IMPORTERS: Dict[str, Type[PlatformImporter]] = {
    ImportPlatform.KAGGLE: KaggleImporter,
    ImportPlatform.HUGGINGFACE: HuggingFaceImporter,
    ImportPlatform.GITHUB: GitHubImporter,
}


def get_importer(platform: str) -> PlatformImporter:
    try:
        return IMPORTERS[str(platform)]()
    except KeyError as exc:
        raise InvalidIdentifierError(f"Unsupported platform: {platform}") from exc


def detect_platform(value: str) -> Optional[str]:
    """Guess the platform from a pasted URL (None for bare identifiers)."""
    raw = (value or "").strip()
    if not raw:
        return None
    host = urlparse(raw if "://" in raw else f"https://{raw}").netloc.lower()
    for platform, importer in IMPORTERS.items():
        if host in importer.hosts:
            return platform
    return None


__all__ = [
    "IMPORTERS",
    "get_importer",
    "detect_platform",
    "PlatformImporter",
    "PlatformDatasetInfo",
    "PlatformImportError",
    "InvalidIdentifierError",
    "PlatformDatasetNotFoundError",
    "PlatformAuthError",
    "PlatformUnavailableError",
    "HuggingFaceImporter",
    "GitHubImporter",
    "KaggleImporter",
]
