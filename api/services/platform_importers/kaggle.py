"""Kaggle dataset importer (metadata only).

One request per import: the dataset *view* endpoint, which answers anonymously
for public datasets and carries everything we store — title, description,
license, tags, owner and last updated. No key is needed. ``KAGGLE_USERNAME`` /
``KAGGLE_KEY`` (settings) are sent as basic auth when configured, which is only
useful for datasets the account can see but the public cannot.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from django.conf import settings

from api.services.platform_importers.base import (
    InvalidIdentifierError,
    PlatformAuthError,
    PlatformDatasetInfo,
    PlatformImporter,
    parse_iso_datetime,
)
from api.utils.enums import ImportPlatform

KAGGLE_HOSTS = ("www.kaggle.com", "kaggle.com")
KAGGLE_API = "https://www.kaggle.com/api/v1"
KAGGLE_WEB = "https://www.kaggle.com/datasets"

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MAX_DESCRIPTION = 1000


class KaggleImporter(PlatformImporter):
    platform = ImportPlatform.KAGGLE
    label = "Kaggle"
    hosts = KAGGLE_HOSTS

    def _auth(self) -> Optional[Tuple[str, str]]:
        """Platform-level credentials if configured; None means anonymous."""
        username = getattr(settings, "KAGGLE_USERNAME", None)
        key = getattr(settings, "KAGGLE_KEY", None)
        return (username, key) if username and key else None

    # -- identifier ---------------------------------------------------------- #
    def parse_identifier(self, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            raise InvalidIdentifierError("Enter a Kaggle dataset ref (owner/dataset) or URL")

        if "://" in raw or raw.startswith(KAGGLE_HOSTS):
            parsed = urlparse(raw if "://" in raw else f"https://{raw}")
            if parsed.netloc.lower() not in KAGGLE_HOSTS:
                raise InvalidIdentifierError("That is not a kaggle.com URL")
            parts = [p for p in parsed.path.split("/") if p]
            if parts and parts[0] == "datasets":
                parts = parts[1:]
            if len(parts) < 2:
                raise InvalidIdentifierError(
                    "Expected a dataset URL like https://www.kaggle.com/datasets/<owner>/<dataset>"
                )
            owner, slug = parts[0], parts[1]
        else:
            parts = raw.strip("/").split("/")
            if len(parts) != 2:
                raise InvalidIdentifierError("Kaggle refs look like 'owner/dataset-name'")
            owner, slug = parts

        if not (_SLUG_RE.match(owner) and _SLUG_RE.match(slug)):
            raise InvalidIdentifierError(
                "Kaggle owner and dataset names use letters, digits, '-' and '_'"
            )
        return f"{owner}/{slug}"

    # -- fetch --------------------------------------------------------------- #
    def fetch_dataset_info(self, identifier: str) -> PlatformDatasetInfo:
        ref = self.parse_identifier(identifier)
        owner, slug = ref.split("/")

        meta: Dict[str, Any] = self._get_json(
            f"{KAGGLE_API}/datasets/view/{owner}/{slug}", auth=self._auth()
        )
        if meta.get("isPrivate"):
            raise PlatformAuthError("This Kaggle dataset is private")

        title = meta.get("title") or slug
        description = (meta.get("description") or meta.get("subtitle") or "").strip()

        return PlatformDatasetInfo(
            platform=self.platform,
            identifier=ref,
            title=str(title)[:300],
            description=description[:MAX_DESCRIPTION],
            source_url=meta.get("url") or f"{KAGGLE_WEB}/{ref}",
            author=str(meta.get("ownerName") or owner)[:300],
            license=self._license(meta),
            tags=self._tags(meta),
            last_updated=parse_iso_datetime(meta.get("lastUpdated")),
            raw=meta,
        )

    # -- pieces -------------------------------------------------------------- #
    @staticmethod
    def _license(meta: Dict[str, Any]) -> str:
        licenses = meta.get("licenses") or []
        if licenses and isinstance(licenses[0], dict):
            return str(licenses[0].get("name") or "")
        return str(meta.get("licenseName") or "")

    @staticmethod
    def _tags(meta: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for entry in meta.get("keywords") or []:
            if isinstance(entry, str) and entry.strip():
                out.append(entry.strip()[:50])
        for entry in meta.get("tags") or []:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if isinstance(name, str) and name.strip() and name.strip() not in out:
                out.append(name.strip()[:50])
        return out[:30]
