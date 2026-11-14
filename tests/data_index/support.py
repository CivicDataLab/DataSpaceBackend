"""Helpers shared by the data-index tests (fixtures live in conftest.py)."""

from pathlib import Path
from typing import Any, List, Optional

import pytest
from django.core.files.base import ContentFile
from django.db import connections

from api.models import Resource

FIXTURES = Path(__file__).parent / "fixtures"
DATA_DB = "data_db"


def uses_data_db(test: Any) -> Any:
    """Mark a test that builds tables in the data database.

    It needs real commits (to see on_commit drops and the switch) and both
    databases. Skipped without TEST_DATA_DB_URL; see conftest.py.
    """
    test = pytest.mark.django_db(transaction=True, databases=["default", DATA_DB])(test)
    return pytest.mark.data_db(test)


def list_public_tables() -> List[str]:
    with connections[DATA_DB].cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return sorted(row[0] for row in cursor.fetchall())


def table_exists(name: str) -> bool:
    with connections[DATA_DB].cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s) IS NOT NULL", [f'public."{name}"'])
        return bool(cursor.fetchone()[0])


def table_rows(name: str, order_by: str = "1") -> List[tuple]:
    with connections[DATA_DB].cursor() as cursor:
        cursor.execute(f'SELECT * FROM "{name}" ORDER BY {order_by}')
        return cursor.fetchall()


def table_comment(name: str) -> Optional[str]:
    with connections[DATA_DB].cursor() as cursor:
        cursor.execute("SELECT obj_description(to_regclass(%s), 'pg_class')", [f'public."{name}"'])
        return cursor.fetchone()[0]


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def replace_file(resource: Resource, csv: Any) -> None:
    """Save a new file for the resource, as an upload request does before indexing."""
    content = fixture_bytes(csv) if isinstance(csv, str) else csv
    details = resource.resourcefiledetails
    details.file = ContentFile(content, name=f"{resource.id.hex}.csv")
    details.size = len(content)
    details.save()
