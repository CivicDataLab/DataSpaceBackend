"""File and image fields have no `path`, and the rest works on S3 (#284).

Root cause: strawberry-django types every FileField/ImageField as its own
`DjangoFileType`/`DjangoImageType`, whose `path` reads `FieldFile.path`, the
file's location on the server's disk. Media moved to S3, which has none, so any
query asking for `path` (on a logo, cover image, resource file, profile picture,
chart image...) got "This backend doesn't support absolute paths." and a null
file object.

Fix: `api/types/file_types.py` registers types with the same GraphQL names and
every other field, without `path` (a disk location is of no use to API clients;
`name` is the storage key and `url` opens the file). The test storage
(`InMemoryStorage`) can build a local path, so the `s3_like` fixture makes it
refuse `path` the way S3 does: nothing left in the types may need one.
"""

import io
import os
import types

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import RequestFactory
from django.utils._os import safe_join
from PIL import Image

from api.models import Collaborative, Organization
from api.schema.schema import schema
from api.utils.enums import CollaborativeStatus
from authorization.models import User

FILE = "{ name url size }"


def png() -> ContentFile:
    buffer = io.BytesIO()
    Image.new("RGB", (3, 2)).save(buffer, format="PNG")
    return ContentFile(buffer.getvalue(), name="logo.png")


def run(user, query):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, context_value=ctx)


def fields_of(sdl: str, type_name: str) -> set[str]:
    body = sdl.split(f"type {type_name} {{")[1].split("}")[0]
    return {line.strip() for line in body.strip().splitlines()}


@pytest.fixture(autouse=True)
def s3_like(monkeypatch):
    """Storages without a local path raise this, as S3 does on dev and prod."""

    def no_local_path(name):
        raise NotImplementedError("This backend doesn't support absolute paths.")

    for alias in ("public", "private"):
        storage = storages[alias]
        # InMemoryStorage finds its files through path(); keep that working inside it
        monkeypatch.setattr(
            storage,
            "_relative_path",
            lambda name, storage=storage: os.path.relpath(
                safe_join(storage.location, name), storage.location
            ),
        )
        monkeypatch.setattr(storage, "path", no_local_path)


@pytest.fixture
def superuser(db):
    return User.objects.create(username="su", keycloak_id="su", is_superuser=True)


@pytest.fixture
def org(db):
    org = Organization.objects.create(name="Org", description="o", slug="org")
    org.logo.save("logo.png", png())
    return org


@pytest.fixture
def collaborative(superuser, org):
    collaborative = Collaborative.objects.create(
        title="co", user=superuser, organization=org, status=CollaborativeStatus.PUBLISHED
    )
    collaborative.logo.save("logo.png", png())
    return collaborative


def test_schema_file_types_have_no_path():
    sdl = schema.as_str()
    for name in ("DjangoFileType", "DjangoImageType"):
        assert sdl.count(f"type {name} {{") == 1, name
    assert fields_of(sdl, "DjangoFileType") == {"name: String!", "size: Int!", "url: String!"}
    assert fields_of(sdl, "DjangoImageType") == {
        "name: String!",
        "size: Int!",
        "url: String!",
        "width: Int!",
        "height: Int!",
    }


def test_asking_for_path_is_refused_as_an_unknown_field(superuser, collaborative):
    result = run(superuser, "{ collaboratives { logo { path } } }")
    assert result.errors
    assert "Cannot query field 'path'" in result.errors[0].message


def test_collaborative_logo_fields_work_on_s3(superuser, collaborative):
    result = run(superuser, f"{{ collaboratives {{ logo {FILE} }} }}")
    assert not result.errors, result.errors
    logo = result.data["collaboratives"][0]["logo"]
    assert logo["name"] == collaborative.logo.name
    assert logo["url"] and logo["size"] > 0


def test_image_width_and_height_still_work(superuser, collaborative):
    result = run(superuser, "{ collaboratives { logo { width height } } }")
    assert not result.errors, result.errors
    assert result.data["collaboratives"][0]["logo"] == {"width": 3, "height": 2}


def test_organization_logo_fields_work_on_s3(superuser, org):
    result = run(superuser, f'{{ organizations(id: "{org.id}") {{ logo {FILE} }} }}')
    assert not result.errors, result.errors
    assert result.data["organizations"][0]["logo"]["name"] == org.logo.name


def test_missing_file_is_null_without_an_error(superuser, collaborative):
    Collaborative.objects.filter(id=collaborative.id).update(logo="")
    result = run(superuser, f"{{ collaboratives {{ logo {FILE} }} }}")
    assert not result.errors, result.errors
    assert result.data["collaboratives"][0]["logo"] is None
