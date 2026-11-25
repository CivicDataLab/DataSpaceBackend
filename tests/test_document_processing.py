"""Processing a resource with DOST-Catalyst starts only when an administrator asks.

These tests cover the request rules (global switch, superuser, PDF only, one
job at a time), the options, the "file changed" check, the Django admin actions
and deletes, and that an upload through the GraphQL API never creates a
processing request. The worker is in test_document_worker.py.
"""

import types
from typing import Any

import pytest
from django.contrib import admin
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from api.admin import ProcessingStatusFilter
from api.models import (
    Dataset,
    Organization,
    ProcessedFile,
    Resource,
    ResourceFileDetails,
    ResourceProcessing,
)
from api.schema.schema import schema
from api.services.document_processing import (
    ProcessingOptions,
    ProcessingRefused,
    cancel_processing,
    request_processing,
)
from api.utils.enums import ProcessedFileKind, ProcessingStatus
from authorization.models import User

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def add_file(resource: Resource, name: str, file_format: str, content: bytes) -> None:
    ResourceFileDetails.objects.create(
        resource=resource, file=ContentFile(content, name=name), format=file_format
    )


@pytest.fixture
def world(db: Any, settings: Any) -> types.SimpleNamespace:
    settings.DOCUMENT_PROCESSING_ENABLED = True
    org = Organization.objects.create(name="Org", description="o", slug="org")
    admin_user = User.objects.create(
        username="admin", keycloak_id="admin", is_superuser=True, is_staff=True
    )
    staff = User.objects.create(username="staff", keycloak_id="staff", is_staff=True)
    dataset = Dataset.objects.create(
        title="Reports", slug="reports", description="d", user=admin_user, organization=org
    )
    pdf = Resource.objects.create(name="report.pdf", dataset=dataset)
    add_file(pdf, "report.pdf", "PDF", PDF_BYTES)
    csv = Resource.objects.create(name="cases.csv", dataset=dataset)
    add_file(csv, "cases.csv", "CSV", b"district,cases\nPune,3\n")
    no_file = Resource.objects.create(name="empty", dataset=dataset)
    return types.SimpleNamespace(
        org=org, admin=admin_user, staff=staff, dataset=dataset, pdf=pdf, csv=csv, no_file=no_file
    )


def refusal(resource: Resource, user: Any) -> str:
    with pytest.raises(ProcessingRefused) as exc:
        request_processing(resource, user)
    return str(exc.value)


class TestRequestRules:
    def test_admin_request_for_a_pdf_waits_for_the_worker(self, world: Any) -> None:
        chosen = ProcessingOptions(use_sarvam=True, language="hi-IN")
        processing = request_processing(world.pdf, world.admin, chosen)

        assert processing.status == ProcessingStatus.REQUESTED
        assert processing.requested_by == world.admin
        assert ProcessingOptions.from_stored(processing.options) == chosen
        assert processing.source_sha256 == world.pdf.resourcefiledetails.sha256
        assert ResourceProcessing.objects.count() == 1

    def test_switch_off_refuses_even_an_admin(self, world: Any, settings: Any) -> None:
        settings.DOCUMENT_PROCESSING_ENABLED = False

        assert refusal(world.pdf, world.admin) == "Document processing is switched off."
        assert not ResourceProcessing.objects.exists()

    def test_staff_user_who_is_not_superuser_is_refused(self, world: Any) -> None:
        assert refusal(world.pdf, world.staff) == "Only an administrator can process documents."

    def test_only_pdf_files_are_processed(self, world: Any) -> None:
        assert "this file is CSV" in refusal(world.csv, world.admin)
        assert refusal(world.no_file, world.admin) == "The resource has no file."
        assert not ResourceProcessing.objects.exists()

    def test_second_request_while_waiting_is_refused(self, world: Any) -> None:
        request_processing(world.pdf, world.admin)

        assert "already waiting for or in processing" in refusal(world.pdf, world.admin)

    def test_new_request_after_a_failure_resets_the_row(self, world: Any) -> None:
        first = request_processing(world.pdf, world.admin)
        ResourceProcessing.objects.filter(pk=first.pk).update(
            status=ProcessingStatus.FAILED, error="Catalyst lost the job.", catalyst_job_id="j1"
        )

        again = request_processing(world.pdf, world.admin)

        assert again.pk == first.pk
        assert again.status == ProcessingStatus.REQUESTED
        assert again.error == ""
        assert again.catalyst_job_id == ""


class TestStale:
    def test_result_is_stale_after_the_file_is_replaced(self, world: Any) -> None:
        processing = request_processing(world.pdf, world.admin)
        ResourceProcessing.objects.filter(pk=processing.pk).update(status=ProcessingStatus.DONE)
        processing.refresh_from_db()
        assert not processing.is_stale

        details = world.pdf.resourcefiledetails
        details.file = ContentFile(PDF_BYTES + b"% second edition\n", name="report-v2.pdf")
        details.save()
        processing = ResourceProcessing.objects.get(pk=processing.pk)

        assert processing.is_stale
        stale = ProcessingStatusFilter(
            None, {"processing": ["stale"]}, Resource, admin.site._registry[Resource]
        ).queryset(None, Resource.objects.all())
        assert list(stale) == [world.pdf]


class TestCancel:
    def test_waiting_request_is_cancelled(self, world: Any) -> None:
        processing = request_processing(world.pdf, world.admin)

        cancelled = cancel_processing(processing, world.admin)

        assert cancelled.status == ProcessingStatus.CANCELLED
        assert cancelled.finished_at is not None

    def test_running_job_is_left_to_the_worker_to_stop(self, world: Any) -> None:
        processing = request_processing(world.pdf, world.admin)
        ResourceProcessing.objects.filter(pk=processing.pk).update(status=ProcessingStatus.RUNNING)

        current = cancel_processing(processing, world.admin)

        assert current.status == ProcessingStatus.RUNNING
        assert current.cancel_requested


class TestOptions:
    def test_language_needs_sarvam_and_a_real_code(self, world: Any) -> None:
        with pytest.raises(ProcessingRefused, match="only with Sarvam"):
            request_processing(world.pdf, world.admin, ProcessingOptions(language="hi-IN"))
        with pytest.raises(ProcessingRefused, match="not a language code"):
            request_processing(
                world.pdf, world.admin, ProcessingOptions(use_sarvam=True, language="hindi")
            )

    def test_options_become_the_catalyst_request(self) -> None:
        assert ProcessingOptions().catalyst_request() == {"dost": {"enabled": True}}
        assert ProcessingOptions(
            full_page_ocr=True, use_sarvam=True, language="mr-IN"
        ).catalyst_request() == {
            "dost": {"enabled": True, "source_language": "mr-IN"},
            "formats": {
                "pdf": {
                    "pipeline_options": {
                        "ocr_options": {
                            "mode": "full_page",
                            "__variant__": "SarvamOcrOptions",
                            "lang": ["mr-IN"],
                        }
                    }
                }
            },
        }


def admin_request(user: User) -> Any:
    request = RequestFactory().post("/admin/api/resource/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class TestAdminAction:
    def resource_admin(self) -> Any:
        return admin.site._registry[Resource]

    def test_action_requests_pdfs_and_reports_what_it_skipped(self, world: Any) -> None:
        request = admin_request(world.admin)

        self.resource_admin().process_documents(request, Resource.objects.all())

        assert list(ResourceProcessing.objects.values_list("resource", flat=True)) == [world.pdf.id]
        texts = [m.message for m in get_messages(request)]
        assert "1 document(s) requested for processing." in texts
        assert any(t.startswith("1 skipped: Only PDF files") for t in texts)
        assert "1 skipped: The resource has no file." in texts

    def test_action_is_offered_only_to_superusers_with_the_switch_on(
        self, world: Any, settings: Any
    ) -> None:
        resource_admin = self.resource_admin()

        assert "process_documents" in resource_admin.get_actions(admin_request(world.admin))
        assert "process_documents" not in resource_admin.get_actions(admin_request(world.staff))
        settings.DOCUMENT_PROCESSING_ENABLED = False
        assert "process_documents" not in resource_admin.get_actions(admin_request(world.admin))


def stored_output(processing: ResourceProcessing) -> ProcessedFile:
    output = ProcessedFile(processing=processing, kind=ProcessedFileKind.TABLES_MD, size=7)
    output.file.save("document_tables.md", ContentFile(b"| a |\n"), save=False)
    output.save()
    assert output.file.storage.exists(output.file.name)
    return output


class TestDeleteOutputs:
    def processing_admin(self) -> Any:
        return admin.site._registry[ResourceProcessing]

    def test_admin_delete_removes_the_stored_files(self, world: Any) -> None:
        processing = request_processing(world.pdf, world.admin)
        ResourceProcessing.objects.filter(pk=processing.pk).update(status=ProcessingStatus.DONE)
        output = stored_output(processing)

        self.processing_admin().delete_queryset(
            admin_request(world.admin), ResourceProcessing.objects.all()
        )

        assert not ResourceProcessing.objects.exists()
        assert not ProcessedFile.objects.exists()
        assert not output.file.storage.exists(output.file.name)

    def test_a_waiting_or_running_job_is_not_deleted(self, world: Any) -> None:
        processing = request_processing(world.pdf, world.admin)
        request = admin_request(world.admin)
        processing_admin = self.processing_admin()

        assert not processing_admin.has_delete_permission(request, processing)
        assert not processing_admin.has_delete_permission(admin_request(world.staff))
        processing_admin.delete_queryset(request, ResourceProcessing.objects.all())

        assert ResourceProcessing.objects.filter(pk=processing.pk).exists()
        assert any("skipped" in m.message for m in get_messages(request))

    def test_deleting_the_resource_removes_its_output_files(self, world: Any) -> None:
        processing = request_processing(world.pdf, world.admin)
        output = stored_output(processing)

        world.pdf.delete()

        assert not ProcessedFile.objects.exists()
        assert not output.file.storage.exists(output.file.name)


CREATE = """mutation ($ds: UUID!, $file: Upload!) {
  createFileResources(fileResourceInput: {dataset: $ds, files: [$file]}) { id }
}"""


def test_uploading_a_pdf_never_starts_processing(world: Any) -> None:
    request = RequestFactory().post("/api/graphql")
    request.user = world.admin
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=world.admin, context={}, response=None)
    upload = SimpleUploadedFile("new.pdf", PDF_BYTES, content_type="application/pdf")

    result = schema.execute_sync(
        CREATE, variable_values={"ds": str(world.dataset.id), "file": upload}, context_value=ctx
    )

    assert result.errors is None, result.errors
    new_id = result.data["createFileResources"][0]["id"]
    assert Resource.objects.get(id=new_id).resourcefiledetails.format == "PDF"
    assert not ResourceProcessing.objects.exists()
