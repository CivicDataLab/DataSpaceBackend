"""The document worker moves requests through DOST-Catalyst and stores the outputs.

A fake Catalyst server (a real HTTP server in a thread) speaks the job API that
the worker uses: POST /api/jobs, GET /api/jobs/{id}, GET of the output files
and DELETE /api/jobs/{id}, behind HTTP Basic auth. The tests drive the worker
one ``step()`` at a time.
"""

import base64
import json
import re
import threading
import types
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from api.models import (
    Dataset,
    Organization,
    ProcessedFile,
    Resource,
    ResourceFileDetails,
    ResourceProcessing,
)
from api.services.catalyst_client import CatalystClient
from api.services.document_processing import cancel_processing, request_processing
from api.services.document_worker import DocumentWorker
from api.utils.enums import ProcessedFileKind, ProcessingStatus
from authorization.models import User

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
OUTPUTS = {
    "dost_tables_md": ("document_tables.md", b"| district | cases |\n"),
    "dost_sentences_csv": ("document_sentences.csv", b"original_sentence\nRain fell.\n"),
    "dost_report_json": ("extraction_report.json", b"{}"),  # kept as `report`, not a file
}


class FakeCatalyst:
    """Just enough of Catalyst's job API, with switches for the failure cases."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.requests: list[tuple[str, str, dict[str, str], bytes]] = []
        self.submit_status = 202
        self.state = "done"
        self.envelope_status = "success"
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> None:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def calls(self, method: str) -> list[tuple[str, str, dict[str, str], bytes]]:
        return [r for r in self.requests if r[0] == method]

    def _envelope(self, job_id: str) -> dict[str, Any]:
        if self.envelope_status != "success":
            return {
                "status": self.envelope_status,
                "outputs": [],
                "errors": [{"component": "convert", "message": "The PDF is damaged."}],
            }
        return {
            "status": "success",
            "outputs": [
                {
                    "format": fmt,
                    "filename": name,
                    "url": f"/api/jobs/{job_id}/files/dost/{name}",
                }
                for fmt, (name, _) in OUTPUTS.items()
            ],
            "dost": {"tables": 1, "sentences": 1},
            "errors": [],
        }

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self
        expected_auth = "Basic " + base64.b64encode(b"dost:secret").decode()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # keep the test output clean
                pass

            def _reply(self, status: int, body: Any = None, raw: bytes = b"") -> None:
                data = json.dumps(body).encode() if body is not None else raw
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _record(self) -> bool:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                fake.requests.append((self.command, self.path, dict(self.headers), body))
                if self.headers.get("Authorization") != expected_auth:
                    self._reply(401, {"detail": "Wrong password"})
                    return False
                return True

            def do_POST(self) -> None:
                if not self._record():
                    return
                if fake.submit_status != 202:
                    self._reply(fake.submit_status, {"detail": "The server is busy."})
                    return
                job_id = f"job{len(fake.jobs) + 1}"
                fake.jobs[job_id] = {}
                self._reply(202, {"job_id": job_id, "state": "waiting", "position": 1})

            def do_GET(self) -> None:
                if not self._record():
                    return
                match = re.fullmatch(r"/api/jobs/([^/]+)(/files/dost/(.+))?", self.path)
                if not match or match.group(1) not in fake.jobs:
                    self._reply(404, {"detail": "Unknown job"})
                    return
                job_id, file_name = match.group(1), match.group(3)
                if file_name:
                    content = {name: data for name, data in OUTPUTS.values()}[file_name]
                    self._reply(200, raw=content)
                    return
                status: dict[str, Any] = {"job_id": job_id, "state": fake.state}
                if fake.state == "done":
                    status["envelope"] = fake._envelope(job_id)
                self._reply(200, status)

            def do_DELETE(self) -> None:
                if not self._record():
                    return
                fake.jobs.pop(self.path.rsplit("/", 1)[-1], None)
                self._reply(204, raw=b"")

        return Handler


@pytest.fixture
def catalyst() -> Iterator[FakeCatalyst]:
    fake = FakeCatalyst()
    fake.start()
    yield fake
    fake.stop()


@pytest.fixture
def world(db: Any, settings: Any, catalyst: FakeCatalyst) -> types.SimpleNamespace:
    settings.DOCUMENT_PROCESSING_ENABLED = True
    admin_user = User.objects.create(username="admin", keycloak_id="admin", is_superuser=True)
    org = Organization.objects.create(name="Org", description="o", slug="org")
    dataset = Dataset.objects.create(
        title="Reports", slug="reports", description="d", user=admin_user, organization=org
    )
    pdf = Resource.objects.create(name="report.pdf", dataset=dataset)
    ResourceFileDetails.objects.create(
        resource=pdf, file=ContentFile(PDF_BYTES, name="report.pdf"), format="PDF"
    )
    worker = DocumentWorker(
        client=CatalystClient(catalyst.url, "dost", "secret", timeout=5),
        max_wait=timedelta(minutes=45),
    )
    return types.SimpleNamespace(admin=admin_user, pdf=pdf, worker=worker)


def processing_of(resource: Resource) -> ResourceProcessing:
    return ResourceProcessing.objects.get(resource=resource)


def test_a_requested_pdf_is_processed_and_its_outputs_stored(
    world: Any, catalyst: FakeCatalyst
) -> None:
    request_processing(world.pdf, world.admin)

    assert world.worker.step()  # sends the PDF
    started = processing_of(world.pdf)
    assert started.status == ProcessingStatus.RUNNING
    assert started.catalyst_job_id == "job1"
    _, _, headers, body = catalyst.calls("POST")[0]
    assert headers["Idempotency-Key"].startswith(f"dataspace-{started.id}-")
    assert b'"dost": {"enabled": true}' in body
    assert PDF_BYTES in body

    assert world.worker.step()  # the job is done: download and store
    done = processing_of(world.pdf)
    assert done.status == ProcessingStatus.DONE
    assert done.report == {"tables": 1, "sentences": 1}
    files = {f.kind: f for f in ProcessedFile.objects.filter(processing=done)}
    assert set(files) == {ProcessedFileKind.TABLES_MD, ProcessedFileKind.SENTENCES_CSV}
    tables = files[ProcessedFileKind.TABLES_MD]
    assert tables.file.name.startswith(f"resources/processed/{world.pdf.id}/")
    assert tables.file.read() == b"| district | cases |\n"
    assert catalyst.calls("DELETE") and "job1" not in catalyst.jobs


def test_nothing_starts_while_the_switch_is_off(
    world: Any, catalyst: FakeCatalyst, settings: Any
) -> None:
    request_processing(world.pdf, world.admin)
    settings.DOCUMENT_PROCESSING_ENABLED = False

    assert not world.worker.step()

    assert processing_of(world.pdf).status == ProcessingStatus.REQUESTED
    assert catalyst.requests == []


def test_a_busy_catalyst_leaves_the_request_waiting(world: Any, catalyst: FakeCatalyst) -> None:
    request_processing(world.pdf, world.admin)
    catalyst.submit_status = 503

    world.worker.step()

    waiting = processing_of(world.pdf)
    assert waiting.status == ProcessingStatus.REQUESTED
    assert waiting.started_at is None


def test_a_failed_conversion_keeps_catalysts_reason(world: Any, catalyst: FakeCatalyst) -> None:
    request_processing(world.pdf, world.admin)
    catalyst.envelope_status = "failure"

    world.worker.step()
    world.worker.step()

    failed = processing_of(world.pdf)
    assert failed.status == ProcessingStatus.FAILED
    assert failed.error == "The PDF is damaged."
    assert not ProcessedFile.objects.exists()


def test_a_job_that_catalyst_lost_fails(world: Any, catalyst: FakeCatalyst) -> None:
    request_processing(world.pdf, world.admin)
    catalyst.state = "running"
    world.worker.step()
    catalyst.jobs.clear()  # as after a Catalyst restart

    world.worker.step()

    failed = processing_of(world.pdf)
    assert failed.status == ProcessingStatus.FAILED
    assert "lost the job" in failed.error


def test_cancelling_a_running_job_stops_it_in_catalyst(world: Any, catalyst: FakeCatalyst) -> None:
    request_processing(world.pdf, world.admin)
    catalyst.state = "running"
    world.worker.step()

    cancel_processing(processing_of(world.pdf), world.admin)
    world.worker.step()

    assert processing_of(world.pdf).status == ProcessingStatus.CANCELLED
    assert [path for _, path, _, _ in catalyst.calls("DELETE")] == ["/api/jobs/job1"]


def test_a_job_that_runs_too_long_fails(world: Any, catalyst: FakeCatalyst) -> None:
    request_processing(world.pdf, world.admin)
    catalyst.state = "running"
    world.worker.step()
    ResourceProcessing.objects.filter(resource=world.pdf).update(
        started_at=timezone.now() - timedelta(hours=1)
    )

    world.worker.step()

    failed = processing_of(world.pdf)
    assert failed.status == ProcessingStatus.FAILED
    assert "within 45 minutes" in failed.error
    assert catalyst.calls("DELETE")


def test_a_new_run_replaces_the_old_outputs(world: Any, catalyst: FakeCatalyst) -> None:
    request_processing(world.pdf, world.admin)
    world.worker.step()
    world.worker.step()
    old = ProcessedFile.objects.get(kind=ProcessedFileKind.TABLES_MD)

    request_processing(world.pdf, world.admin)
    world.worker.step()
    world.worker.step()

    assert not ProcessedFile.objects.filter(pk=old.pk).exists()
    assert ProcessedFile.objects.count() == 2  # one tables file, one sentences file
    new = ProcessedFile.objects.get(kind=ProcessedFileKind.TABLES_MD)
    assert new.file.read() == b"| district | cases |\n"
