"""Every tabular upload gets its own table, named from its own row id.

Root cause this guards against: table names used to be built from the resource
name and dataset title (up to 110 characters). Postgres keeps only the first 63
bytes of a name, so two resources with long, similar names shared one table and
a re-upload of one replaced the other's data.
"""

import json
import uuid
from datetime import datetime, timezone

from api.models import ResourceDataTable
from api.utils.data_indexing import index_resource_data
from api.utils.data_table_names import data_table_name, physical_table_name
from api.utils.data_tables import build_data_table, describe_data_table
from tests.data_index.support import uses_data_db

LEGACY_NAME = (
    "district-wise-prevalence-of-anaemia-among-women-aged-15-49-"
    "district-health-indicators-assam-nfhs-5_1a2b3c4d"
)


def test_a_table_name_is_rdt_and_the_row_id_in_lowercase_hex() -> None:
    row_id = uuid.UUID("0123456789ABCDEF0123456789ABCDEF")
    assert data_table_name(row_id) == "rdt_0123456789abcdef0123456789abcdef"
    assert len(data_table_name(row_id)) == 36


def test_physical_name_is_cut_to_63_bytes_like_postgres() -> None:
    assert len(LEGACY_NAME) > 100
    assert physical_table_name(LEGACY_NAME) == LEGACY_NAME[:63]
    short = data_table_name(uuid.uuid4())
    assert physical_table_name(short) == short


def test_physical_name_never_cuts_a_character_in_half() -> None:
    # 62 ASCII bytes then a 2-byte character: Postgres keeps 62 bytes, not 63.
    name = "a" * 62 + "é" + "tail"
    assert physical_table_name(name) == "a" * 62


def test_a_new_row_is_named_from_its_own_id(add_resource: object) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    row = ResourceDataTable.objects.create(resource=resource)
    assert row.table_name == "rdt_" + row.id.hex


def test_an_existing_row_keeps_its_stored_name_on_save(add_resource: object) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    row = ResourceDataTable.objects.create(resource=resource, table_name=LEGACY_NAME)
    row.save()
    row.refresh_from_db()
    assert row.table_name == LEGACY_NAME


@uses_data_db
def test_two_resources_with_long_similar_names_get_their_own_tables(
    add_resource: object, tables: object
) -> None:
    prefix = "District wise prevalence of anaemia among women aged 15 to 49 "
    first = add_resource(prefix + "(NFHS-4)", "districts_v1.csv")
    second = add_resource(prefix + "(NFHS-5)", "districts_v2.csv")

    first_row = index_resource_data(first)
    second_row = index_resource_data(second)

    assert first_row is not None and second_row is not None
    assert first_row.table_name != second_row.table_name
    assert [r[1] for r in tables.rows(first_row.table_name)] == [30, 10, 20]
    assert len(tables.rows(second_row.table_name)) == 4


@uses_data_db
def test_the_table_comment_is_stored_as_text_not_run_as_sql(
    add_resource: object, tables: object
) -> None:
    import pandas as pd

    resource = add_resource("cases'; DROP TABLE x; --\"", "districts_v1.csv")
    built_at = datetime(2026, 11, 13, 10, 30, tzinfo=timezone.utc)
    comment = describe_data_table(resource, built_at=built_at)

    build_data_table("rdt_comment_check", pd.DataFrame({"a": [1]}), comment)

    stored = json.loads(tables.comment("rdt_comment_check"))
    assert stored == {
        "resource_id": str(resource.id),
        "resource": "cases'; DROP TABLE x; --\"",
        "dataset": "District health indicators",
        "built_at": "2026-11-13T10:30:00+00:00",
    }
