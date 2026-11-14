"""Deleting a data-table row drops its table once the delete commits.

Root cause this guards against: deleting a resource or a dataset never removed
its data tables, so the data database kept every table ever built. The one
receiver on the row's delete also covers re-uploads and admin deletes.
"""

import os
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import patch

import psycopg2
from django.db import connections, transaction
from structlog.testing import capture_logs

from api.models import ResourceDataTable
from api.signals.data_table_signals import drop_table_after_row_delete
from api.utils.data_indexing import index_resource_data
from api.utils.data_tables import drop_data_table_if_unshared
from tests.data_index.support import uses_data_db

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_PREFIX = "district-wise-prevalence-of-anaemia-among-women-aged-15-49-dist"  # 63 bytes


def create_legacy_table(name: str) -> None:
    with connections["data_db"].cursor() as cursor:
        cursor.execute(f'CREATE TABLE "{name}" (district text)')


@uses_data_db
def test_deleting_a_resource_drops_its_table(add_resource: Any, tables: Any) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    row = index_resource_data(resource)

    resource.delete()

    assert not tables.exists(row.table_name)


@uses_data_db
def test_deleting_a_dataset_drops_every_table_of_its_resources(
    add_resource: Any, dataset: Any, tables: Any
) -> None:
    index_resource_data(add_resource("first.csv", "districts_v1.csv"))
    index_resource_data(add_resource("second.csv", "districts_v2.csv"))
    assert len(tables.names()) == 2

    dataset.delete()

    assert tables.names() == []


@uses_data_db
def test_a_rolled_back_delete_keeps_the_table(add_resource: Any, tables: Any) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    row = index_resource_data(resource)

    try:
        with transaction.atomic():
            resource.delete()
            raise RuntimeError("the request failed after the delete")
    except RuntimeError:
        pass

    assert ResourceDataTable.objects.filter(pk=row.pk).exists()
    assert tables.exists(row.table_name)


@uses_data_db
def test_a_legacy_table_two_rows_share_is_dropped_only_with_the_last_row(
    add_resource: Any, tables: Any
) -> None:
    first = ResourceDataTable.objects.create(
        resource=add_resource("first.csv", "districts_v1.csv"),
        table_name=SHARED_PREFIX + "rict-health-indicators-nfhs-4_1a2b3c4d",
    )
    second = ResourceDataTable.objects.create(
        resource=add_resource("second.csv", "districts_v1.csv"),
        table_name=SHARED_PREFIX + "rict-health-indicators-nfhs-5_5e6f7a8b",
    )
    create_legacy_table(first.table_name)
    assert tables.names() == [SHARED_PREFIX]

    with capture_logs() as logs:
        first.delete()
    assert tables.names() == [SHARED_PREFIX]
    assert any(log["event"] == "data_table_drop_skipped_shared" for log in logs)

    second.delete()
    assert tables.names() == []


@uses_data_db
def test_dropping_a_table_that_is_already_gone_does_not_fail_the_delete(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    ResourceDataTable.objects.create(resource=resource, table_name="rdt_never_built")

    resource.delete()

    assert not ResourceDataTable.objects.filter(resource_id=resource.pk).exists()


@uses_data_db
def test_a_drop_blocked_by_a_reader_is_logged_and_the_delete_still_succeeds(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    row = index_resource_data(resource)
    settings = connections["data_db"].settings_dict
    reader = psycopg2.connect(
        dbname=settings["NAME"],
        user=settings["USER"],
        password=settings["PASSWORD"],
        host=settings["HOST"],
        port=settings["PORT"],
    )
    try:
        with reader.cursor() as cursor:
            cursor.execute(f'LOCK TABLE "{row.table_name}" IN ACCESS SHARE MODE')

        with patch("api.utils.data_tables.DROP_LOCK_TIMEOUT", "200ms"), capture_logs() as logs:
            resource.delete()
    finally:
        reader.rollback()
        reader.close()

    assert not ResourceDataTable.objects.filter(pk=row.pk).exists()
    assert tables.exists(row.table_name)
    failures = [log for log in logs if log["event"] == "data_table_drop_failed"]
    assert failures and failures[0]["table_name"] == row.table_name


def test_the_receiver_schedules_one_guarded_drop_per_deleted_row(add_resource: Any) -> None:
    first = ResourceDataTable.objects.create(resource=add_resource("a.csv", "districts_v1.csv"))
    second = ResourceDataTable.objects.create(resource=add_resource("b.csv", "districts_v1.csv"))
    expected = [(first.table_name, first.pk), (second.table_name, second.pk)]

    with patch("api.signals.data_table_signals.transaction.on_commit") as on_commit:
        ResourceDataTable.objects.filter(pk__in=[first.pk, second.pk]).delete()

    assert on_commit.call_count == 2
    scheduled = []
    for call in on_commit.call_args_list:
        callback = call.args[0]
        assert isinstance(callback, partial)
        assert callback.func is drop_data_table_if_unshared
        assert call.kwargs == {"using": "default", "robust": True}
        scheduled.append(callback.args)
    assert sorted(scheduled) == sorted(expected)


def test_the_receiver_is_connected_once_the_app_loads() -> None:
    # A fresh interpreter: an import elsewhere in this test run can't connect it for us.
    check = (
        "import django; django.setup()\n"
        "from django.db.models.signals import post_delete\n"
        "from api.models import ResourceDataTable\n"
        "receivers = post_delete._live_receivers(ResourceDataTable)[0]\n"
        "names = {(r.__module__, r.__name__) for r in receivers}\n"
        "print(('api.signals.data_table_signals', 'drop_table_after_row_delete') in names)\n"
    )
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "tests.test_settings"}
    env.pop("TEST_DATA_DB_URL", None)
    result = subprocess.run(
        [sys.executable, "-c", check],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "True"
    assert drop_table_after_row_delete.__module__ == "api.signals.data_table_signals"
