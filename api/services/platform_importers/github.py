"""GitHub repository importer (metadata only).

A repo (optionally a branch and sub-folder) is treated as a dataset. Three
small requests per import: the repo metadata, the branch head (for the
revision) and the README. Public repos need no
token; ``GITHUB_TOKEN`` (settings) is sent when present, mainly to lift the
anonymous 60 requests/hour rate limit.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from django.conf import settings

from api.services.platform_importers.base import (
    InvalidIdentifierError,
    PlatformDatasetInfo,
    PlatformImporter,
    PlatformImportError,
    parse_iso_datetime,
    shorten,
)
from api.utils.enums import ImportPlatform

GITHUB_HOSTS = ("github.com", "www.github.com")
GITHUB_API = "https://api.github.com"
GITHUB_WEB = "https://github.com"

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
MAX_DESCRIPTION = 1000


class GitHubImporter(PlatformImporter):
    platform = ImportPlatform.GITHUB
    label = "GitHub"
    hosts = GITHUB_HOSTS

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        token = getattr(settings, "GITHUB_TOKEN", None)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # -- identifier ---------------------------------------------------------- #
    def parse_identifier(self, value: str) -> str:
        """Normalise to ``owner/repo`` or ``owner/repo@branch:sub/path``."""
        owner, repo, branch, path = self._parse(value)
        ident = f"{owner}/{repo}"
        if branch:
            ident += f"@{branch}"
        if path:
            ident += f":{path}"
        return ident

    def _parse(self, value: str) -> Tuple[str, str, Optional[str], str]:
        raw = (value or "").strip()
        if not raw:
            raise InvalidIdentifierError("Enter a GitHub repository (owner/repo) or URL")

        branch: Optional[str] = None
        path = ""
        if "://" in raw or raw.startswith(GITHUB_HOSTS):
            parsed = urlparse(raw if "://" in raw else f"https://{raw}")
            if parsed.netloc.lower() not in GITHUB_HOSTS:
                raise InvalidIdentifierError("That is not a github.com URL")
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) < 2:
                raise InvalidIdentifierError(
                    "Expected a repository URL like https://github.com/<owner>/<repo>"
                )
            owner, repo = parts[0], parts[1].removesuffix(".git")
            # /tree/<branch>/<path...> or /blob/<branch>/<path...>
            if len(parts) >= 4 and parts[2] in ("tree", "blob"):
                branch = parts[3]
                path = "/".join(parts[4:])
        else:
            spec = raw.strip("/")
            if ":" in spec:
                spec, path = spec.split(":", 1)
            if "@" in spec:
                spec, branch = spec.split("@", 1)
            parts = spec.split("/")
            if len(parts) != 2:
                raise InvalidIdentifierError(
                    "GitHub repos look like 'owner/repo' (optionally owner/repo@branch:path)"
                )
            owner, repo = parts

        if not (_NAME_RE.match(owner) and _NAME_RE.match(repo)):
            raise InvalidIdentifierError(
                "GitHub owner and repo names use letters, digits, '-', '_' and '.'"
            )
        return owner, repo, (branch or None), path.strip("/")

    # -- fetch --------------------------------------------------------------- #
    def fetch_dataset_info(self, identifier: str) -> PlatformDatasetInfo:
        owner, repo, branch, sub_path = self._parse(identifier)
        headers = self._headers()

        meta: Dict[str, Any] = self._get_json(f"{GITHUB_API}/repos/{owner}/{repo}", headers=headers)
        if meta.get("disabled"):
            raise PlatformImportError("This repository has been disabled on GitHub")
        branch = branch or meta.get("default_branch") or "main"
        full_name = meta.get("full_name") or f"{owner}/{repo}"

        # Repo names are slugs ("covid-19-data"); make a readable title from them.
        title = repo.replace("-", " ").replace("_", " ").strip()
        if sub_path:
            title = f"{title} / {sub_path}"

        source_url = f"{GITHUB_WEB}/{full_name}"
        if sub_path:
            source_url += f"/tree/{branch}/{sub_path}"

        readme = self._readme(full_name, headers) or str(meta.get("description") or "")
        license_info = meta.get("license") or {}

        return PlatformDatasetInfo(
            platform=self.platform,
            identifier=self.parse_identifier(identifier),
            title=title[:300],
            description=shorten(readme, MAX_DESCRIPTION),
            source_url=source_url,
            author=str((meta.get("owner") or {}).get("login") or owner)[:300],
            license=str(license_info.get("spdx_id") or license_info.get("name") or ""),
            tags=[t[:50] for t in (meta.get("topics") or []) if isinstance(t, str)][:30],
            last_updated=parse_iso_datetime(meta.get("pushed_at") or meta.get("updated_at")),
            created_at=parse_iso_datetime(meta.get("created_at")),
            revision=self._head_sha(full_name, branch, headers),
            readme=readme,
            homepage=str(meta.get("homepage") or "")[:500],
            is_archived=bool(meta.get("archived")),
        )

    # -- pieces -------------------------------------------------------------- #
    def _readme(self, full_name: str, headers: Dict[str, str]) -> str:
        try:
            response = self._get(
                f"{GITHUB_API}/repos/{full_name}/readme",
                headers={**headers, "Accept": "application/vnd.github.raw"},
            )
            return response.text.strip()
        except PlatformImportError:
            return ""

    def _head_sha(self, full_name: str, branch: str, headers: Dict[str, str]) -> str:
        """Commit SHA at the branch head; empty if the lookup fails."""
        try:
            ref: Dict[str, Any] = self._get_json(
                f"{GITHUB_API}/repos/{full_name}/git/ref/heads/{branch}", headers=headers
            )
            return str((ref.get("object") or {}).get("sha") or "")[:64]
        except PlatformImportError:
            return ""
