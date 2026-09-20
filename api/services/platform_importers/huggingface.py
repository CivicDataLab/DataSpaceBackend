"""Hugging Face Hub dataset importer (metadata only).

Two requests per import: the repo metadata and the README (dataset card).
Public datasets need no token; ``HF_TOKEN`` (settings) is sent when present so
gated/private repos the token can see also work.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from django.conf import settings

from api.services.platform_importers.base import (
    InvalidIdentifierError,
    PlatformAuthError,
    PlatformDatasetInfo,
    PlatformImporter,
    PlatformImportError,
    parse_iso_datetime,
)
from api.utils.enums import ImportPlatform

HF_HOSTS = ("huggingface.co", "www.huggingface.co", "hf.co")
HF_API = "https://huggingface.co/api/datasets"
HF_WEB = "https://huggingface.co/datasets"

# "namespace/name" or a canonical "name"; HF ids allow letters, digits, - _ .
_ID_RE = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9._-]*/)?[A-Za-z0-9][A-Za-z0-9._-]*$")

MAX_DESCRIPTION = 1000  # Dataset.description column length


class HuggingFaceImporter(PlatformImporter):
    platform = ImportPlatform.HUGGINGFACE
    label = "Hugging Face"
    hosts = HF_HOSTS

    def _headers(self) -> Dict[str, str]:
        token = getattr(settings, "HF_TOKEN", None)
        return {"Authorization": f"Bearer {token}"} if token else {}

    # -- identifier ---------------------------------------------------------- #
    def parse_identifier(self, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            raise InvalidIdentifierError("Enter a Hugging Face dataset id or URL")

        if "://" in raw or raw.startswith(tuple(HF_HOSTS)):
            parsed = urlparse(raw if "://" in raw else f"https://{raw}")
            if parsed.netloc.lower() not in HF_HOSTS:
                raise InvalidIdentifierError("That is not a huggingface.co URL")
            parts = [p for p in parsed.path.split("/") if p]
            if not parts or parts[0] != "datasets":
                raise InvalidIdentifierError(
                    "Expected a dataset URL like https://huggingface.co/datasets/<namespace>/<name>"
                )
            parts = parts[1:]
            # Trim sub-paths such as /tree/main, /blob/main/..., /viewer.
            if len(parts) >= 2 and parts[1] not in (
                "tree",
                "blob",
                "viewer",
                "resolve",
                "discussions",
            ):
                repo_id = f"{parts[0]}/{parts[1]}"
            elif parts:
                repo_id = parts[0]
            else:
                raise InvalidIdentifierError("Could not find a dataset id in that URL")
        else:
            repo_id = raw[len("datasets/") :] if raw.startswith("datasets/") else raw

        repo_id = repo_id.strip("/")
        if not _ID_RE.match(repo_id):
            raise InvalidIdentifierError(
                "Hugging Face ids look like 'namespace/name' (letters, digits, '-', '_', '.')"
            )
        return repo_id

    # -- fetch --------------------------------------------------------------- #
    def fetch_dataset_info(self, identifier: str) -> PlatformDatasetInfo:
        repo_id = self.parse_identifier(identifier)
        headers = self._headers()

        try:
            meta: Dict[str, Any] = self._get_json(f"{HF_API}/{repo_id}", headers=headers)
        except PlatformAuthError as exc:
            # Hugging Face answers 401 for repos that do not exist as well as
            # for private/gated ones, so say both.
            raise PlatformAuthError(
                f"'{repo_id}' was not found on Hugging Face, or it is private/gated. "
                "Check the spelling; only public datasets can be imported."
            ) from exc
        if meta.get("disabled"):
            raise PlatformImportError("This dataset has been disabled on Hugging Face")

        card: Dict[str, Any] = meta.get("cardData") or {}
        tags: List[str] = meta.get("tags") or []

        title = card.get("pretty_name") or repo_id.split("/")[-1]
        author = meta.get("author") or (repo_id.split("/")[0] if "/" in repo_id else "")

        return PlatformDatasetInfo(
            platform=self.platform,
            identifier=repo_id,
            title=str(title)[:300],
            description=self._description(repo_id, meta, headers),
            source_url=f"{HF_WEB}/{repo_id}",
            author=str(author)[:300],
            license=self._license(card, tags),
            tags=self._tags(tags),
            last_updated=parse_iso_datetime(meta.get("lastModified")),
            raw=meta,
        )

    # -- pieces -------------------------------------------------------------- #
    @staticmethod
    def _license(card: Dict[str, Any], tags: List[str]) -> str:
        lic = card.get("license")
        if isinstance(lic, list):
            lic = lic[0] if lic else ""
        if lic:
            return str(lic)
        for tag in tags:
            if tag.startswith("license:"):
                return tag[len("license:") :]
        return ""

    @staticmethod
    def _tags(tags: List[str]) -> List[str]:
        """Keep human-meaningful tags: plain ones plus task/language values."""
        out: List[str] = []
        for tag in tags:
            if ":" not in tag:
                value = tag
            else:
                prefix, _, value = tag.partition(":")
                if prefix not in ("task_categories", "language", "task_ids"):
                    continue
            value = value.strip()
            if value and value not in out:
                out.append(value[:50])
        return out[:30]

    def _description(self, repo_id: str, meta: Dict[str, Any], headers: Dict[str, str]) -> str:
        """Prefer the dataset card body (README) over the terse API field."""
        try:
            response = self._get(f"{HF_WEB}/{repo_id}/resolve/main/README.md", headers=headers)
            text = response.text
        except PlatformImportError:
            text = ""
        if text:
            # Strip YAML front matter.
            if text.startswith("---"):
                end = text.find("\n---", 3)
                if end != -1:
                    text = text[end + 4 :]
            text = text.strip()
        if not text:
            text = str(meta.get("description") or "")
        return text[:MAX_DESCRIPTION]
