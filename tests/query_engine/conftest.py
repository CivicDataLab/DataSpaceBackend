"""Shared fixtures for the query-engine data-layer tests.

Builders for the corpus (organisations, datasets, resources, collaboratives,
sectors), Keycloak introspection answers in ``fixtures/`` (hand-built in
Keycloak 26's documented shape with the real client id and role; to be
replaced by answers captured from dev Keycloak, an ops task), and an API
client that sends a bearer token whose introspection the test chooses.

Every test starts from known query-engine settings, so a developer's .env
(or CI's copy of .env.example) never changes what a test sees.
"""

import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, Optional
from unittest import mock

import pytest
from rest_framework.test import APIClient

from api.models import (
    Collaborative,
    Dataset,
    Organization,
    Resource,
    ResourceDataTable,
    Sector,
)
from api.utils.enums import (
    CollaborativeStatus,
    DatasetAccessType,
    DatasetStatus,
    DatasetType,
)
from authorization.models import User

FIXTURES = Path(__file__).parent / "fixtures"
SERVICE_CLIENT_ID = "dataspace-query-engine-service"
SERVICE_ROLE = "query-engine-service"


@pytest.fixture(autouse=True)
def qe_settings(settings: Any) -> Any:
    """Known query-engine settings and an in-memory cache for every test."""
    settings.QE_SERVICE_CLIENT_ID = SERVICE_CLIENT_ID
    settings.QE_SERVICE_ROLE = SERVICE_ROLE
    settings.QE_PLATFORM_SECTORS = []
    settings.QE_ENABLED_COLLABORATIVES = []
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"qe-tests-{uuid.uuid4().hex}",
        }
    }
    return settings


@pytest.fixture
def owner(db: Any) -> User:
    return User.objects.create(username="qe-owner", keycloak_id="qe-owner", email="o@example.org")


@pytest.fixture
def org(db: Any) -> Organization:
    return Organization.objects.create(name="Health Org", description="o", slug="health-org")


@pytest.fixture
def make_dataset(owner: User, org: Organization) -> Callable[..., Dataset]:
    """A dataset, by default in the corpus (published, public, data)."""

    def make(
        title: str = "District health indicators",
        status: str = DatasetStatus.PUBLISHED,
        access_type: str = DatasetAccessType.PUBLIC,
        dataset_type: str = DatasetType.DATA,
        sectors: Iterable[Sector] = (),
    ) -> Dataset:
        dataset = Dataset.objects.create(
            title=title,
            description=f"About {title}",
            user=owner,
            organization=org,
            status=status,
            access_type=access_type,
            dataset_type=dataset_type,
        )
        if sectors:
            dataset.sectors.set(list(sectors))
        return dataset

    return make


@pytest.fixture
def make_resource() -> Callable[..., Resource]:
    """A resource; with a data-table row unless ``with_table=False`` (no physical table)."""

    def make(
        dataset: Dataset,
        name: str = "Indicators by district",
        with_table: bool = True,
        is_active: bool = True,
    ) -> Resource:
        resource = Resource.objects.create(dataset=dataset, name=name, is_active=is_active)
        if with_table:
            ResourceDataTable.objects.create(resource=resource)
        return resource

    return make


@pytest.fixture
def make_collaborative(owner: User) -> Callable[..., Collaborative]:
    def make(
        title: str = "FemHealth",
        status: str = CollaborativeStatus.PUBLISHED,
        datasets: Iterable[Dataset] = (),
    ) -> Collaborative:
        collaborative = Collaborative.objects.create(title=title, user=owner, status=status)
        if datasets:
            collaborative.datasets.set(list(datasets))
        return collaborative

    return make


@pytest.fixture
def make_sector(db: Any) -> Callable[..., Sector]:
    def make(name: str, parent: Optional[Sector] = None) -> Sector:
        return Sector.objects.create(name=name, parent_id=parent)

    return make


def introspection(name: str, expires_in: int = 300, **changes: Any) -> Dict[str, Any]:
    """A captured introspection answer (``service`` or ``end_user``), valid for ``expires_in`` s."""
    data = json.loads((FIXTURES / f"introspection_{name}.json").read_text())
    now = int(time.time())
    data.update(iat=now, exp=now + expires_in)
    data.update(changes)
    return data


def without_role(info: Dict[str, Any], role: str = SERVICE_ROLE) -> Dict[str, Any]:
    changed = copy.deepcopy(info)
    changed["realm_access"]["roles"] = [r for r in changed["realm_access"]["roles"] if r != role]
    return changed


# Tokens the tests send, and what Keycloak says about each.
TOKENS: Dict[str, Callable[[], Dict[str, Any]]] = {
    "service-token": lambda: introspection("service"),
    "end-user-token": lambda: introspection("end_user"),
    "admin-token": lambda: introspection(
        "end_user",
        realm_access={"roles": ["default-roles-dataspace", "admin", "dataspace-admin"]},
    ),
    "inactive-token": lambda: {"active": False},
}


@pytest.fixture
def keycloak_introspect() -> Iterator[mock.MagicMock]:
    """Keycloak's introspection, answering per token from TOKENS (unknown tokens are inactive)."""

    def answer(token: str, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return TOKENS.get(token, lambda: {"active": False})()

    with mock.patch(
        "api.utils.keycloak_utils.keycloak_manager.keycloak_openid.introspect",
        side_effect=answer,
    ) as introspect:
        yield introspect


@pytest.fixture
def api(keycloak_introspect: mock.MagicMock) -> Callable[[Optional[str]], APIClient]:
    """An API client sending ``Bearer <token>`` (no header when token is None)."""

    def client(token: Optional[str] = "service-token") -> APIClient:
        api_client = APIClient()
        if token is not None:
            api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return api_client

    return client
