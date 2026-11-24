"""A small HTTP client for the DOST-Catalyst job API.

All Catalyst details stay in this module:

* ``POST /api/jobs``: the file and a ConvertRequest as JSON; 202 with a job ID;
* ``GET /api/jobs/{id}``: ``state`` is waiting, running or done; when done, the
  ``envelope`` lists the output files;
* ``GET /api/jobs/{id}/files/...``: one output file;
* ``DELETE /api/jobs/{id}``: cancels a job and deletes its files.

Catalyst deletes job files after its ``job_ttl_minutes`` (60 by default), so
the worker downloads them as soon as a job is done.
"""

import json
from dataclasses import dataclass, field
from typing import IO, Any

import requests
from django.conf import settings


class CatalystError(Exception):
    """Catalyst refused the request or answered with an error."""


class CatalystBusy(CatalystError):
    """Catalyst cannot take the job now (its waiting line is full, or it is down)."""


class CatalystJobLost(CatalystError):
    """Catalyst does not know the job, for example after a restart."""


def _detail(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    return str(detail or response.text[:300] or response.reason)


@dataclass
class CatalystClient:
    base_url: str
    username: str
    password: str
    timeout: float = 60.0
    session: requests.Session = field(default_factory=requests.Session)

    @classmethod
    def from_settings(cls) -> "CatalystClient":
        return cls(
            base_url=settings.CATALYST_URL,
            username=settings.CATALYST_USERNAME,
            password=settings.CATALYST_PASSWORD,
        )

    def _url(self, path: str) -> str:
        # Catalyst returns root-relative file URLs; keep a path prefix of CATALYST_URL.
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

    def _send(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        try:
            return self.session.request(
                method,
                self._url(path),
                auth=(self.username, self.password),
                timeout=self.timeout,
                **kwargs,
            )
        except requests.ConnectionError as exc:
            raise CatalystBusy(f"Catalyst is not reachable: {exc}") from exc
        except requests.Timeout as exc:
            raise CatalystBusy(f"Catalyst did not answer in time: {exc}") from exc

    def submit(
        self, filename: str, content: IO[bytes], options: dict[str, Any], idempotency_key: str
    ) -> str:
        """Put the file in Catalyst's waiting line and return the job ID."""
        response = self._send(
            "POST",
            "/api/jobs",
            files={"file": (filename, content, "application/pdf")},
            data={"options": json.dumps(options)},
            headers={"Idempotency-Key": idempotency_key},
        )
        if response.status_code in (429, 503):
            raise CatalystBusy(f"Catalyst is busy: {_detail(response)}")
        if response.status_code != 202:
            raise CatalystError(
                f"Catalyst refused the job ({response.status_code}): " f"{_detail(response)}"
            )
        return str(response.json()["job_id"])

    def status(self, job_id: str) -> dict[str, Any]:
        """The JobStatus of the job: ``state``, and ``envelope`` when done."""
        response = self._send("GET", f"/api/jobs/{job_id}")
        if response.status_code == 404:
            raise CatalystJobLost(f"Catalyst does not know job {job_id}.")
        if response.status_code in (429, 503):
            raise CatalystBusy(f"Catalyst is busy: {_detail(response)}")
        if response.status_code != 200:
            raise CatalystError(
                f"Catalyst status error ({response.status_code}): " f"{_detail(response)}"
            )
        result: dict[str, Any] = response.json()
        return result

    def download(self, url: str) -> bytes:
        """One output file, by the ``url`` of an envelope output."""
        response = self._send("GET", url)
        if response.status_code == 404:
            raise CatalystJobLost(f"Catalyst no longer has {url}.")
        if response.status_code != 200:
            raise CatalystError(
                f"Catalyst download error ({response.status_code}): " f"{_detail(response)}"
            )
        return response.content

    def delete(self, job_id: str) -> None:
        """Cancel the job and delete its files; a job Catalyst no longer knows is fine."""
        response = self._send("DELETE", f"/api/jobs/{job_id}")
        if response.status_code not in (204, 404):
            raise CatalystError(
                f"Catalyst delete error ({response.status_code}): " f"{_detail(response)}"
            )
