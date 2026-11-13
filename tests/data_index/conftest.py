"""Shared setup for the data-index tests.

Tests marked ``data_db`` build real tables in a Postgres data database. They
need TEST_DATA_DB_URL (see tests/test_settings.py), for example:

    docker run -d --name dataspace-test-data-db -e POSTGRES_PASSWORD=postgres \
        -p 55432:5432 postgres:16
    export TEST_DATA_DB_URL=postgres://postgres:postgres@localhost:55432/postgres

Without it they are skipped, unless REQUIRE_DATA_DB_TESTS=1 (set in CI), in
which case the run fails: a green run that skipped them proves nothing.

The main database stays SQLite, so row locks are no-ops here; the lock order is
proven by the flow tests and its effect by the journey script.
"""

import os
import types
from typing import Any, Callable, List, Optional

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connections

from api.models import Dataset, Organization, Resource, ResourceFileDetails
from authorization.models import User
from tests.data_index.support import (
    DATA_DB,
    fixture_bytes,
    list_public_tables,
    table_comment,
    table_exists,
    table_rows,
)


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    if DATA_DB in settings.DATABASES:
        return
    data_db_items = [item for item in items if item.get_closest_marker("data_db")]
    if not data_db_items:
        return
    if os.environ.get("REQUIRE_DATA_DB_TESTS") == "1":
        raise pytest.UsageError(
            f"{len(data_db_items)} data_db tests would be skipped: set TEST_DATA_DB_URL "
            "(REQUIRE_DATA_DB_TESTS=1 forbids skipping them)."
        )
    skip = pytest.mark.skip(reason="needs TEST_DATA_DB_URL (a Postgres data database)")
    for item in data_db_items:
        item.add_marker(skip)


@pytest.fixture(autouse=True)
def empty_data_db_after_test(request: pytest.FixtureRequest, django_db_blocker: Any) -> Any:
    """Drop every table a data_db test left behind.

    pytest-django only empties tables of models routed to a database, and none
    are routed to the data database, so without this each test would see the
    tables of the tests before it.
    """
    yield
    if not request.node.get_closest_marker("data_db") or DATA_DB not in settings.DATABASES:
        return
    with django_db_blocker.unblock():
        for name in list_public_tables():
            with connections[DATA_DB].cursor() as cursor:
                cursor.execute(f'DROP TABLE IF EXISTS "{name}" CASCADE')


@pytest.fixture
def tables() -> types.SimpleNamespace:
    """Read-only peeks into the test data database."""
    return types.SimpleNamespace(
        names=list_public_tables, exists=table_exists, rows=table_rows, comment=table_comment
    )


@pytest.fixture
def owner(db: Any) -> User:
    return User.objects.create(username="owner", keycloak_id="owner")


@pytest.fixture
def dataset(owner: User) -> Dataset:
    org = Organization.objects.create(name="Org", description="o", slug="org")
    return Dataset.objects.create(
        title="District health indicators",
        slug="dhi",
        description="d",
        user=owner,
        organization=org,
    )


@pytest.fixture
def add_resource(dataset: Dataset) -> Callable[..., Resource]:
    """Create a resource holding a CSV file (fixture file name or raw bytes)."""

    def add(name: str, csv: Any, in_dataset: Optional[Dataset] = None) -> Resource:
        content = fixture_bytes(csv) if isinstance(csv, str) else csv
        resource = Resource.objects.create(name=name, dataset=in_dataset or dataset)
        ResourceFileDetails.objects.create(
            resource=resource,
            file=ContentFile(content, name=f"{resource.id.hex}.csv"),
            size=len(content),
            format="csv",
        )
        return resource

    return add
