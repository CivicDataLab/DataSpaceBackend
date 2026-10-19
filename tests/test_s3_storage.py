"""Regression tests for the move from local disk (and DVC) to S3-only media.

Root cause: uploads lived on local disk under MEDIA_ROOT and several code paths
read them through ``FieldFile.path`` (data indexing, upload MIME validation,
search documents, DVC versioning). S3 has no local path, so each of those
would raise ``NotImplementedError`` once media moved to a bucket. DVC never
worked at all: files were never under ``DVC_REPO_PATH``, so every DVC call
raised and ``createMajorVersion`` always failed.

Fix: media goes through two S3 storages (``public``/``private``, keys prefixed
by ``STORAGE_ENV``); readers that need a real file use ``local_copy()``; old
``/public/<name>`` links redirect to public files only; DVC is removed and
``createMajorVersion`` writes the version row directly behind a permission
check. Stored names drop the ``files/public/``/``files/`` prefix left from the
disk layout (S3 keys already sit under ``<env>/public``); ``migrate_media_to_s3``
moves existing files to those names and repoints the rows.
"""

import io
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from django.apps import apps
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models
from django.test import RequestFactory
from django.urls import resolve
from storages.backends.s3 import S3Storage

from api.models import Dataset, Resource, ResourceFileDetails, ResourceVersion
from api.models.Organization import Organization
from api.schema.schema import schema
from api.utils.file_paths import (
    _chart_image_directory_path,
    _organization_directory_path,
    _publication_block_directory_path,
)
from api.utils.file_utils import check_mime_type, local_copy
from api.utils.storage import normalize_media_name, private_storage, public_storage
from api.views.legacy_media import legacy_media_redirect
from authorization.models import User
from DataSpace import settings as project_settings

FAKE_KEYS = {"access_key": "AKIAEXAMPLEKEY000000", "secret_key": "not-a-real-secret"}


def _s3(options):
    # URL building and presigning are local operations; no request reaches AWS.
    return S3Storage(**{**options, **FAKE_KEYS})


class TestS3StorageOptions:
    def test_public_urls_are_unsigned_under_env_public_prefix(self):
        url = _s3(project_settings._S3_PUBLIC_OPTIONS).url("organizations/a/logo.png")
        assert url.endswith(f"/{project_settings.STORAGE_ENV}/public/organizations/a/logo.png")
        assert "X-Amz-Signature" not in url

    def test_private_urls_are_presigned_for_five_minutes(self):
        url = _s3(project_settings._S3_PRIVATE_OPTIONS).url("resources/data.csv")
        assert f"/{project_settings.STORAGE_ENV}/private/resources/data.csv" in url
        assert "X-Amz-Signature" in url
        assert "X-Amz-Expires=300" in url

    def test_default_storage_is_private(self):
        assert project_settings.STORAGES["default"] == project_settings.STORAGES["private"]

    def test_s3_has_no_local_path(self):
        with pytest.raises(NotImplementedError):
            _s3(project_settings._S3_PRIVATE_OPTIONS).path("resources/data.csv")


# A new file field that forgets storage= silently lands in the private default,
# so a public image would 403. Keep this list in step with the models.
PRIVATE_FILE_FIELDS = {
    ("api", "resourcefiledetails", "file"),
    ("api", "resourcechartimage", "image"),
}


class TestFileFieldStorages:
    def _file_fields(self):
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if isinstance(field, models.FileField):
                    yield (model._meta.app_label, model._meta.model_name, field.name), field

    def test_every_file_field_names_public_or_private_storage(self):
        for key, field in self._file_fields():
            assert field._storage_callable in (public_storage, private_storage), key

    def test_only_resource_files_and_chart_images_are_private(self):
        private = {
            key for key, field in self._file_fields() if field._storage_callable is private_storage
        }
        assert private == PRIVATE_FILE_FIELDS


@pytest.mark.django_db
class TestLocalCopy:
    def _stored(self, name, content):
        dataset = Dataset.objects.create(title="Local copy")
        resource = Resource.objects.create(dataset=dataset, name="r", slug=f"r-{name}")
        details = ResourceFileDetails(resource=resource, format="csv")
        details.file.save(name, ContentFile(content), save=False)
        return details.file

    def test_yields_a_local_file_with_the_stored_bytes_and_extension(self):
        fieldfile = self._stored("data.csv", b"a,b\n1,2\n")
        with local_copy(fieldfile) as path:
            assert path.endswith(".csv")
            assert Path(path).read_bytes() == b"a,b\n1,2\n"

    def test_removes_the_temp_file_even_when_the_caller_raises(self):
        fieldfile = self._stored("boom.csv", b"x")
        with pytest.raises(RuntimeError):
            with local_copy(fieldfile) as path:
                raise RuntimeError("boom")
        assert not Path(path).exists()

    def test_mime_check_reads_a_stored_file_without_a_path(self):
        fieldfile = self._stored("report.pdf", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        assert check_mime_type(fieldfile) == "application/pdf"


class TestLegacyMediaRedirect:
    def _get(self, name):
        return legacy_media_redirect(RequestFactory().get(f"/public/{name}"), name)

    def test_route_points_at_the_redirect_view(self):
        assert resolve("/public/files/public/x.png").func is legacy_media_redirect

    def test_public_file_redirects_to_its_storage_url(self):
        name = public_storage().save("organizations/acme/png/logo.png", ContentFile(b"png"))
        response = self._get(name)
        assert response.status_code == 302
        assert response["Location"] == public_storage().url(name)

    def test_old_prefixed_link_redirects_to_the_renamed_file(self):
        name = public_storage().save("organizations/old/png/logo.png", ContentFile(b"png"))
        response = self._get(f"files/public/{name}")
        assert response.status_code == 302
        assert response["Location"] == public_storage().url(name)

    def test_private_file_is_never_redirected(self):
        name = private_storage().save("resources/secret.csv", ContentFile(b"a,b"))
        assert self._get(name).status_code == 404

    @pytest.mark.parametrize("name", ["../etc/passwd", "files/../../etc/passwd", "/etc/passwd"])
    def test_traversal_is_rejected(self, name):
        assert self._get(name).status_code == 404


MAJOR_VERSION = """
mutation($input: CreateMajorVersionInput!) {
  createMajorVersion(input: $input) { ... on TypeResource { id } }
}
"""


@pytest.mark.django_db
class TestCreateMajorVersionWithoutDvc:
    @pytest.fixture
    def owner(self):
        return User.objects.create(username="owner", keycloak_id="owner")

    @pytest.fixture
    def resource(self, owner):
        dataset = Dataset.objects.create(title="Versioned", user=owner)
        return Resource.objects.create(dataset=dataset, name="data", slug="data-versioned")

    def _run(self, user, resource):
        return schema.execute_sync(
            MAJOR_VERSION,
            variable_values={"input": {"resourceId": str(resource.id), "description": "schema"}},
            context_value=types.SimpleNamespace(user=user, context={}),
        )

    def test_owner_gets_a_version_row_and_bump(self, owner, resource):
        result = self._run(owner, resource)
        assert result.errors is None, result.errors
        resource.refresh_from_db()
        assert resource.version == "v1.0.0"
        assert ResourceVersion.objects.filter(resource=resource, version_number="v1.0.0").exists()

    def test_a_stranger_cannot_version_someone_elses_resource(self, resource):
        stranger = User.objects.create(username="stranger", keycloak_id="stranger")
        result = self._run(stranger, resource)
        assert result.errors
        assert not ResourceVersion.objects.filter(resource=resource).exists()


class TestNameLayout:
    def test_upload_names_carry_no_legacy_prefix(self):
        org = types.SimpleNamespace(name="Acme")
        chart = types.SimpleNamespace(name="Rain")
        block = types.SimpleNamespace(publication_id="p1")
        assert _organization_directory_path(org, "logo.png") == "organizations/Acme/png/logo.png"
        assert _chart_image_directory_path(chart, "c.png") == "chart_images/Rain/png/c.png"
        assert _publication_block_directory_path(block, "r.pdf").startswith("publications/p1/")

    @pytest.mark.parametrize(
        "old, new",
        [
            ("files/public/organizations/a/png/l.png", "organizations/a/png/l.png"),
            ("files/use_case/Health/logo/l.png", "use_case/Health/logo/l.png"),
            ("resources/data.csv", "resources/data.csv"),
        ],
    )
    def test_normalize_media_name(self, old, new):
        assert normalize_media_name(old) == new


@pytest.mark.django_db
class TestMigrateMediaToS3:
    OLD = "files/public/organizations/acme/png/logo.png"
    NEW = "organizations/acme/png/logo.png"

    @pytest.fixture
    def storage(self):
        storage = Organization._meta.get_field("logo").storage
        for name in (self.OLD, self.NEW):
            if storage.exists(name):
                storage.delete(name)
        return storage

    @pytest.fixture
    def source(self, tmp_path):
        logo = tmp_path / self.OLD
        logo.parent.mkdir(parents=True)
        logo.write_bytes(b"logo-bytes")
        (tmp_path / "stray.txt").write_text("no row points here")
        return tmp_path

    @pytest.fixture
    def org(self, storage):
        return Organization.objects.create(name="Acme", slug="acme", logo=self.OLD)

    def _run(self, *args):
        out = io.StringIO()
        call_command("migrate_media_to_s3", *args, stdout=out)
        return out.getvalue()

    def _read(self, storage, name):
        with storage.open(name) as fh:
            return fh.read()

    def test_dry_run_writes_nothing(self, source, storage, org):
        output = self._run("--source", str(source))
        assert "copied_from_disk=1" in output and "rows_renamed=1" in output
        assert not storage.exists(self.NEW)
        org.refresh_from_db()
        assert org.logo.name == self.OLD

    def test_disk_file_lands_under_the_clean_name_and_row_follows(self, source, storage, org):
        assert "copied_from_disk=1" in self._run("--source", str(source), "--execute")
        assert self._read(storage, self.NEW) == b"logo-bytes"
        org.refresh_from_db()
        assert org.logo.name == self.NEW
        assert "in_place=1" in self._run("--source", str(source), "--execute")

    def test_old_s3_key_is_copied_to_the_clean_name(self, storage, org):
        storage.save(self.OLD, ContentFile(b"from-s3"))
        assert "moved_in_s3=1" in self._run("--execute")
        assert self._read(storage, self.NEW) == b"from-s3"
        assert storage.exists(self.OLD)  # nothing is deleted
        org.refresh_from_db()
        assert org.logo.name == self.NEW

    def test_counts_missing_and_orphaned_files(self, source, storage, org):
        Organization.objects.create(name="Gone", slug="gone", logo="files/public/gone.png")
        output = self._run("--source", str(source))
        assert "missing=1" in output
        assert "orphaned=1" in output

    def test_a_missing_file_keeps_its_row_name(self, storage):
        gone = Organization.objects.create(name="Gone", slug="gone", logo="files/public/gone.png")
        self._run("--execute")
        gone.refresh_from_db()
        assert gone.logo.name == "files/public/gone.png"

    def test_a_failed_copy_exits_non_zero(self, source, storage, org):
        with patch.object(storage, "save", side_effect=OSError("denied")):
            with pytest.raises(CommandError):
                self._run("--source", str(source), "--execute")
        org.refresh_from_db()
        assert org.logo.name == self.OLD
