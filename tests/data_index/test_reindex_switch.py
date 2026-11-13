"""Re-uploads build the new table first and switch over in one commit.

Root causes this guards against:
- The old table was dropped before the new one existed, so readers saw empty or
  half-written data, and a failed re-upload lost the data for good.
- The column-row rebuild swallowed errors per column. Inside the switch's
  transaction one failure silently rolled everything back while the upload
  still reported success.
- Two overlapping uploads of one resource each indexed their own file, and the
  slower (older) one could switch in last, so the download and the served rows
  disagreed.
"""

from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from django.db import connections, transaction
from django.db.utils import ProgrammingError
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from api.models import Resource, ResourceDataTable, ResourceSchema
from api.utils import data_tables
from api.utils.data_indexing import index_resource_data
from api.utils.data_tables import (
    FileIdentity,
    LoadedFile,
    has_indexable_file,
    load_resource_frame,
    rebuild_resource_schema,
)
from tests.data_index.support import fixture_bytes, replace_file, uses_data_db

# --- Layer 1: the real flow against both databases --------------------------


@uses_data_db
def test_first_upload_creates_a_named_table_with_its_columns(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")

    row = index_resource_data(resource)

    assert row is not None and row.table_name == "rdt_" + row.id.hex
    assert ResourceDataTable.objects.get(resource=resource).table_name == row.table_name
    assert tables.rows(row.table_name) == [("Jorhat", 30), ("Kamrup", 10), ("Nagaon", 20)]
    assert list(
        ResourceSchema.objects.filter(resource=resource)
        .order_by("id")
        .values_list("field_name", "format")
    ) == [("district", "STRING"), ("cases", "INTEGER")]
    assert str(resource.id) in tables.comment(row.table_name)
    assert "cases.csv" in tables.comment(row.table_name)


@uses_data_db
def test_reupload_switches_to_a_new_table_and_drops_the_old_one(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    old = index_resource_data(resource)
    ResourceSchema.objects.filter(resource=resource, field_name="cases").update(
        description="Confirmed cases"
    )

    replace_file(resource, "districts_v2.csv")
    new = index_resource_data(resource)

    assert new is not None and new.table_name != old.table_name
    assert ResourceDataTable.objects.get(resource=resource).pk == new.pk
    assert len(tables.rows(new.table_name)) == 4
    assert not tables.exists(old.table_name)
    assert tables.names() == [new.table_name]
    assert (
        ResourceSchema.objects.get(resource=resource, field_name="cases").description
        == "Confirmed cases"
    )


@uses_data_db
def test_readers_see_the_complete_old_table_until_the_switch_commits(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    old = index_resource_data(resource)
    replace_file(resource, "districts_v2.csv")
    seen: dict = {}
    real_lock = data_tables.lock_resource
    real_drop = data_tables.drop_data_table_if_unshared

    def spy_lock(res: Resource) -> None:
        new_tables = [t for t in tables.names() if t != old.table_name]
        seen["new_rows_at_switch"] = len(tables.rows(new_tables[0]))
        seen["old_exists_at_switch"] = tables.exists(old.table_name)
        # The lock only holds inside the switch's transaction (Postgres refuses it outside).
        seen["lock_inside_transaction"] = transaction.get_connection().in_atomic_block
        real_lock(res)

    def spy_drop(table_name: str, row_id: Any) -> None:
        seen["dropped"] = table_name
        seen["open_transaction_at_drop"] = transaction.get_connection().in_atomic_block
        seen["new_row_saved_at_drop"] = (
            ResourceDataTable.objects.get(resource=resource).table_name != old.table_name
        )
        real_drop(table_name, row_id)

    with (
        patch("api.utils.data_indexing.lock_resource", spy_lock),
        patch("api.signals.data_table_signals.drop_data_table_if_unshared", spy_drop),
    ):
        new = index_resource_data(resource)

    assert new is not None
    assert seen == {
        "new_rows_at_switch": 4,
        "old_exists_at_switch": True,
        "lock_inside_transaction": True,
        "dropped": old.table_name,
        "open_transaction_at_drop": False,
        "new_row_saved_at_drop": True,
    }


@uses_data_db
def test_a_failed_build_keeps_the_old_data_and_leaves_no_table(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    old = index_resource_data(resource)

    # A count past the BIGINT range: the copy into the new table fails midway.
    replace_file(resource, "out_of_range.csv")
    with capture_logs() as logs:
        assert index_resource_data(resource) is None

    assert ResourceDataTable.objects.get(resource=resource).pk == old.pk
    assert tables.names() == [old.table_name]
    assert len(tables.rows(old.table_name)) == 3
    # The failure is logged by its code, never by the offending cell's value.
    failures = [log for log in logs if log["event"] == "data_index_failed"]
    assert failures and failures[0]["error_code"] == "22003"
    assert failures[0]["where"].startswith("data_tables.py:")
    assert "18446744073709551615" not in repr(logs)


@uses_data_db
def test_a_header_too_long_for_the_column_list_fails_the_switch_and_keeps_the_old_data(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    old = index_resource_data(resource)
    old_columns = list(
        ResourceSchema.objects.filter(resource=resource).values_list("field_name", flat=True)
    )

    replace_file(resource, "long_header.csv")
    assert index_resource_data(resource) is None

    assert ResourceDataTable.objects.get(resource=resource).pk == old.pk
    assert tables.names() == [old.table_name]
    assert (
        list(ResourceSchema.objects.filter(resource=resource).values_list("field_name", flat=True))
        == old_columns
    )


@uses_data_db
def test_a_reader_still_holding_the_old_name_gets_does_not_exist_not_new_rows(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    stale = index_resource_data(resource)
    replace_file(resource, "districts_v2.csv")
    index_resource_data(resource)

    with pytest.raises(ProgrammingError, match="does not exist"):
        with connections["data_db"].cursor() as cursor:
            cursor.execute(f'SELECT * FROM "{stale.table_name}"')


@uses_data_db
def test_a_slower_build_of_an_older_file_backs_off_when_a_newer_file_was_saved(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    real_build = data_tables.build_data_table
    newer: dict = {}

    def build_then_newer_upload_lands(table_name: str, frame: pd.DataFrame, comment: str) -> None:
        real_build(table_name, frame, comment)
        if newer:
            return  # the other request's own build
        newer["started"] = True
        # Meanwhile another request saves a newer file and finishes indexing it.
        other_request = Resource.objects.get(pk=resource.pk)
        replace_file(other_request, "districts_v2.csv")
        newer["row"] = index_resource_data(other_request)

    with patch("api.utils.data_indexing.build_data_table", build_then_newer_upload_lands):
        assert index_resource_data(resource) is None

    current = ResourceDataTable.objects.get(resource=resource)
    assert current.pk == newer["row"].pk
    assert tables.names() == [current.table_name]
    assert len(tables.rows(current.table_name)) == 4


@uses_data_db
def test_indexing_inside_an_outer_transaction_is_refused(add_resource: Any, tables: Any) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")

    with capture_logs() as logs, transaction.atomic():
        assert index_resource_data(resource) is None

    assert tables.names() == []
    assert not ResourceDataTable.objects.filter(resource=resource).exists()
    assert any(log["event"] == "data_index_refused_inside_transaction" for log in logs)


@uses_data_db
def test_reupload_keeps_the_datasets_default_table(
    add_resource: Any, owner: Any, dataset: Any
) -> None:
    first = add_resource("first.csv", "districts_v1.csv")
    second = add_resource("second.csv", "districts_v2.csv")
    first_row = index_resource_data(first)
    index_resource_data(second)

    replace_file(first, "districts_v2.csv")
    replaced = index_resource_data(first)

    assert replaced is not None and replaced.created == first_row.created
    assert ResourceDataTable.objects.get(pk=replaced.pk).created == first_row.created
    client = APIClient()
    client.force_authenticate(owner)
    response = client.get(f"/api/datasets/{dataset.id}/data/")
    assert response.status_code == 200, response.content
    assert response.json()["resource_id"] == str(first.id)


# --- Layer 1: helpers on the main database only ------------------------------


def test_a_resource_without_a_supported_file_is_not_indexable(add_resource: Any) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    assert has_indexable_file(resource)

    resource.resourcefiledetails.format = "pdf"
    assert not has_indexable_file(resource)

    bare = Resource.objects.create(name="empty", dataset=resource.dataset)
    assert not has_indexable_file(bare)


def test_load_remembers_which_stored_file_it_read(add_resource: Any) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    details = resource.resourcefiledetails

    loaded = load_resource_frame(resource)

    assert loaded is not None
    assert loaded.file == FileIdentity(details.file.name, details.sha256)
    assert list(loaded.frame.columns) == ["district", "cases"]


def test_load_returns_nothing_for_a_file_with_only_a_header(add_resource: Any) -> None:
    resource = add_resource("cases.csv", b"district,cases\n")
    assert load_resource_frame(resource) is None


def test_load_cleans_quotes_line_breaks_and_duplicate_headers(add_resource: Any) -> None:
    # pandas renames plain duplicates itself; these two only collide once the quote goes.
    resource = add_resource("cases.csv", b'"dis""trict","a\nb","x""",x\nKamrup,1,2,3\n')
    loaded = load_resource_frame(resource)
    assert loaded is not None
    assert list(loaded.frame.columns) == ["district", "a b", "x", "x_1"]


def test_rebuild_columns_lets_a_database_error_escape(add_resource: Any) -> None:
    from django.db import DatabaseError

    resource = add_resource("cases.csv", "districts_v1.csv")
    frame = pd.DataFrame({"district": ["Kamrup"], "cases": [1]})

    def failing_create(**kwargs: Any) -> None:
        raise DatabaseError("value too long for type character varying(255)")

    with patch.object(ResourceSchema.objects, "create", failing_create):
        with pytest.raises(DatabaseError):
            rebuild_resource_schema(resource, frame)


def test_rebuild_columns_refuses_a_header_longer_than_the_column_list_allows(
    add_resource: Any,
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    frame = pd.DataFrame({"district": ["Kamrup"], "x" * 256: [1]})
    with pytest.raises(ValueError, match="column 2"):
        rebuild_resource_schema(resource, frame)
    assert not ResourceSchema.objects.filter(resource=resource).exists()


# --- Layer 3: the flow's order and clean-up (helpers mocked) -----------------

FLOW_HELPERS = [
    "is_inside_transaction",
    "has_indexable_file",
    "load_resource_frame",
    "new_data_table_row",
    "describe_data_table",
    "build_data_table",
    "lock_resource",
    "stored_file_identity",
    "retire_data_table_row",
    "save_data_table_row",
    "rebuild_resource_schema",
    "data_table_row_exists",
    "drop_data_table",
]
FILE = FileIdentity("resources/cases.csv", "abc123")


@pytest.fixture
def flow() -> Any:
    """Every helper the flow calls, mocked on one parent so call order is recorded."""
    parent = MagicMock()
    patchers = [
        patch(f"api.utils.data_indexing.{name}", getattr(parent, name)) for name in FLOW_HELPERS
    ]
    for p in patchers:
        p.start()
    parent.is_inside_transaction.return_value = False
    parent.has_indexable_file.return_value = True
    parent.load_resource_frame.return_value = LoadedFile(pd.DataFrame({"a": [1]}), FILE)
    parent.new_data_table_row.return_value = MagicMock(table_name="rdt_new", pk="new-id")
    parent.stored_file_identity.return_value = FILE
    parent.retire_data_table_row.return_value = datetime(2026, 1, 1, tzinfo=timezone.utc)
    parent.data_table_row_exists.return_value = True
    yield parent
    for p in patchers:
        p.stop()


def called(flow: Any) -> List[str]:
    return [c[0] for c in flow.mock_calls if "." not in c[0]]


def test_flow_builds_then_locks_before_retiring_the_old_row(flow: Any) -> None:
    row = index_resource_data(MagicMock())

    assert row is flow.new_data_table_row.return_value
    assert called(flow) == [
        "is_inside_transaction",
        "has_indexable_file",
        "load_resource_frame",
        "new_data_table_row",
        "describe_data_table",
        "build_data_table",
        "lock_resource",
        "stored_file_identity",
        "retire_data_table_row",
        "save_data_table_row",
        "rebuild_resource_schema",
        "data_table_row_exists",
    ]
    flow.save_data_table_row.assert_called_once_with(
        flow.new_data_table_row.return_value, created=flow.retire_data_table_row.return_value
    )


def raise_error(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("boom")


@pytest.mark.parametrize(
    "helper",
    ["build_data_table", "lock_resource", "retire_data_table_row", "rebuild_resource_schema"],
)
def test_flow_drops_its_table_when_a_step_fails(flow: Any, helper: str) -> None:
    getattr(flow, helper).side_effect = raise_error

    assert index_resource_data(MagicMock()) is None

    flow.drop_data_table.assert_called_once_with("rdt_new")


def test_flow_drops_its_table_when_a_newer_file_was_saved(flow: Any) -> None:
    flow.stored_file_identity.return_value = FileIdentity("resources/newer.csv", "def456")

    assert index_resource_data(MagicMock()) is None

    flow.retire_data_table_row.assert_not_called()
    flow.drop_data_table.assert_called_once_with("rdt_new")


def test_flow_drops_its_table_when_the_new_row_is_missing_after_the_commit(flow: Any) -> None:
    flow.data_table_row_exists.return_value = False

    assert index_resource_data(MagicMock()) is None

    flow.drop_data_table.assert_called_once_with("rdt_new")


def test_flow_drops_its_table_even_when_interrupted(flow: Any) -> None:
    flow.build_data_table.side_effect = KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        index_resource_data(MagicMock())

    flow.drop_data_table.assert_called_once_with("rdt_new")


def test_flow_keeps_the_table_after_a_confirmed_switch(flow: Any) -> None:
    index_resource_data(MagicMock())
    flow.drop_data_table.assert_not_called()


@pytest.mark.parametrize("stop_at", ["inside_transaction", "no_file", "nothing_loaded"])
def test_flow_builds_nothing_when_there_is_nothing_to_index(flow: Any, stop_at: str) -> None:
    if stop_at == "inside_transaction":
        flow.is_inside_transaction.return_value = True
    elif stop_at == "no_file":
        flow.has_indexable_file.return_value = False
    else:
        flow.load_resource_frame.return_value = None

    assert index_resource_data(MagicMock()) is None

    flow.build_data_table.assert_not_called()
    flow.drop_data_table.assert_not_called()
