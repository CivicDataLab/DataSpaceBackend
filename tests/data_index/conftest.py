"""Shared setup for the data-index tests.

Tests marked ``data_db`` build real tables in a Postgres data database; the
skip-or-fail hook and the per-test table clean-up for them live in
tests/conftest.py (shared with tests/query_engine/).

The main database stays SQLite, so row locks are no-ops here; the lock order is
proven by the flow tests and its effect by the journey script.
"""

import types
from typing import Any, Callable, Optional

import pytest
from django.core.files.base import ContentFile

from api.models import Dataset, Organization, Resource, ResourceFileDetails
from authorization.models import User
from tests.data_index.support import (
    fixture_bytes,
    list_public_tables,
    table_comment,
    table_exists,
    table_rows,
)


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
