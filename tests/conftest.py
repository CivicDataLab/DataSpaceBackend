"""Setup shared by every test folder that builds tables in the data database.

Tests marked ``data_db`` (decorate them with ``uses_data_db`` from
tests/data_index/support.py) build real tables in a Postgres data database.
They need TEST_DATA_DB_URL (see tests/test_settings.py), for example:

    docker run -d --name dataspace-test-data-db -e POSTGRES_PASSWORD=postgres \
        -p 55432:5432 postgres:16
    export TEST_DATA_DB_URL=postgres://postgres:postgres@localhost:55432/postgres

Without it they are skipped, unless REQUIRE_DATA_DB_TESTS=1 (set in CI), in
which case the run fails: a green run that skipped them proves nothing.

Used by tests/data_index/ and tests/query_engine/.
"""

import os
from typing import Any, List

import pytest
from django.conf import settings
from django.db import connections

from tests.data_index.support import DATA_DB, list_public_tables


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
