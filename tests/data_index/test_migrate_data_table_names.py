"""The one-off command that moves existing data tables to per-upload names.

Root cause it cleans up after: tables used to be named from the resource name
and dataset title, cut by Postgres to 63 bytes, so two resources could share
one table (one of them serving the other's data). Short names can't have
collided and are renamed in place; long names may already hold another
resource's data and are rebuilt from each resource's own file.
"""

import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pandas as pd
import psycopg2
import pytest
from django.core.management import CommandError, call_command
from django.db import connections

from api.models import AccessModel, AccessModelResource, ResourceDataTable
from api.utils.data_table_migration import (
    DataTableRow,
    find_orphans,
    rename_legacy_table,
)
from api.utils.data_table_names import data_table_name
from api.utils.data_tables import DataDbTable, build_data_table
from tests.data_index.support import uses_data_db

SHORT_LEGACY = "casescsv_district-health-indicators_1a2b3c4d"
SHARED_PREFIX = "district-wise-prevalence-of-anaemia-among-women-aged-15-49-dist"  # 63 bytes
LONG_FIRST = SHARED_PREFIX + "rict-health-indicators-nfhs-4_1a2b3c4d"
LONG_SECOND = SHARED_PREFIX + "rict-health-indicators-nfhs-5_5e6f7a8b"
WRONG_ROWS = [("Somewhere else", 999)]


def legacy_table(name: str, rows: List[tuple]) -> None:
    """A table as the old code built it (Postgres cuts the name to 63 bytes)."""
    with connections["data_db"].cursor() as cursor:
        cursor.execute(f'CREATE TABLE "{name}" (district text, cases bigint)')
        for row in rows:
            cursor.execute(f'INSERT INTO "{name}" VALUES (%s, %s)', list(row))


def legacy_row(resource: Any, name: str) -> ResourceDataTable:
    return ResourceDataTable.objects.create(resource=resource, table_name=name)


def run_command(*args: str, report: Path) -> str:
    out = StringIO()
    call_command("migrate_data_table_names", *args, "--report", str(report), stdout=out)
    return out.getvalue()


def read_report(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def outcomes(report: Dict[str, Any]) -> Dict[str, str]:
    return {entry["table_name"]: entry["outcome"] for entry in report["rows"]}


def current_table(resource: Any) -> str:
    return ResourceDataTable.objects.get(resource=resource).table_name


def remove_stored_file(resource: Any) -> None:
    details = resource.resourcefiledetails
    details.file.storage.delete(details.file.name)


# --- Layer 1: the command against both databases -----------------------------


@uses_data_db
def test_a_short_legacy_table_is_renamed_only_on_apply(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    row = legacy_row(resource, SHORT_LEGACY)
    legacy_table(SHORT_LEGACY, [("Kamrup", 10), ("Nagaon", 20)])

    run_command(report=tmp_path / "dry.json")
    assert current_table(resource) == SHORT_LEGACY
    assert tables.names() == [SHORT_LEGACY]
    assert outcomes(read_report(tmp_path / "dry.json")) == {SHORT_LEGACY: "planned_rename"}

    run_command("--apply", report=tmp_path / "apply.json")
    assert current_table(resource) == data_table_name(row.id)
    assert tables.names() == [data_table_name(row.id)]
    assert tables.rows(data_table_name(row.id)) == [("Kamrup", 10), ("Nagaon", 20)]
    assert json.loads(tables.comment(data_table_name(row.id)))["resource_id"] == str(resource.id)


@uses_data_db
def test_a_table_two_rows_shared_is_rebuilt_from_each_resources_own_file(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    first = add_resource("first.csv", "districts_v1.csv")
    second = add_resource("second.csv", "districts_v2.csv")
    legacy_row(first, LONG_FIRST)
    legacy_row(second, LONG_SECOND)
    legacy_table(LONG_SECOND, [("Kamrup", 11)])  # the second upload overwrote the first's data

    run_command("--apply", report=tmp_path / "apply.json")

    assert outcomes(read_report(tmp_path / "apply.json")) == {
        LONG_FIRST: "rebuilt",
        LONG_SECOND: "rebuilt",
    }
    assert len(tables.rows(current_table(first))) == 3
    assert len(tables.rows(current_table(second))) == 4
    assert sorted(tables.names()) == sorted([current_table(first), current_table(second)])


@uses_data_db
def test_a_long_legacy_table_with_one_row_left_is_rebuilt_not_renamed(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    resource = add_resource("first.csv", "districts_v1.csv")
    legacy_row(resource, LONG_FIRST)
    legacy_table(LONG_FIRST, WRONG_ROWS)  # its former sharer, since deleted, overwrote it

    run_command("--apply", report=tmp_path / "apply.json")

    assert tables.rows(current_table(resource)) == [("Jorhat", 30), ("Kamrup", 10), ("Nagaon", 20)]
    assert tables.names() == [current_table(resource)]


@uses_data_db
def test_a_long_legacy_table_whose_file_is_gone_is_renamed_and_marked_unverified(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    resource = add_resource("first.csv", "districts_v1.csv")
    row = legacy_row(resource, LONG_FIRST)
    legacy_table(LONG_FIRST, WRONG_ROWS)
    remove_stored_file(resource)

    run_command("--apply", report=tmp_path / "apply.json")

    assert outcomes(read_report(tmp_path / "apply.json")) == {LONG_FIRST: "unverified"}
    assert current_table(resource) == data_table_name(row.id)
    assert tables.rows(data_table_name(row.id)) == WRONG_ROWS
    assert json.loads(tables.comment(data_table_name(row.id)))["unverified"] is True

    # Every later run still lists it, though the row itself now looks migrated.
    run_command(report=tmp_path / "later.json")
    later = read_report(tmp_path / "later.json")
    assert outcomes(later) == {data_table_name(row.id): "already_migrated"}
    assert [t["resource_id"] for t in later["unverified_tables"]] == [str(resource.id)]


@uses_data_db
def test_a_sharing_row_whose_file_is_gone_stays_put_while_the_other_moves(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    first = add_resource("first.csv", "districts_v1.csv")
    second = add_resource("second.csv", "districts_v2.csv")
    legacy_row(first, LONG_FIRST)
    legacy_row(second, LONG_SECOND)
    legacy_table(LONG_SECOND, [("Kamrup", 11)])
    remove_stored_file(first)

    run_command("--apply", report=tmp_path / "apply.json")

    assert outcomes(read_report(tmp_path / "apply.json")) == {
        LONG_FIRST: "missing_file",
        LONG_SECOND: "rebuilt",
    }
    assert current_table(first) == LONG_FIRST
    assert SHARED_PREFIX in tables.names()  # still used by the first row
    assert len(tables.rows(current_table(second))) == 4


@uses_data_db
def test_a_rerun_after_a_crash_between_rename_and_row_update_just_updates_the_row(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    row = legacy_row(resource, SHORT_LEGACY)
    legacy_table(SHORT_LEGACY, [("Kamrup", 10)])
    with connections["data_db"].cursor() as cursor:
        cursor.execute(f'ALTER TABLE "{SHORT_LEGACY}" RENAME TO "{data_table_name(row.id)}"')

    run_command("--apply", report=tmp_path / "apply.json")

    assert outcomes(read_report(tmp_path / "apply.json")) == {SHORT_LEGACY: "row_updated"}
    assert current_table(resource) == data_table_name(row.id)
    assert tables.rows(data_table_name(row.id)) == [("Kamrup", 10)]


@uses_data_db
def test_a_rename_blocked_by_a_reader_is_skipped_then_finished_on_a_rerun(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    row = legacy_row(resource, SHORT_LEGACY)
    legacy_table(SHORT_LEGACY, [("Kamrup", 10)])
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
            cursor.execute(f'LOCK TABLE "{SHORT_LEGACY}" IN ACCESS SHARE MODE')
        with patch("api.utils.data_table_migration.RENAME_LOCK_TIMEOUT", "200ms"):
            run_command("--apply", report=tmp_path / "blocked.json")
    finally:
        reader.rollback()
        reader.close()

    assert outcomes(read_report(tmp_path / "blocked.json")) == {SHORT_LEGACY: "skipped_lock"}
    assert current_table(resource) == SHORT_LEGACY

    run_command("--apply", report=tmp_path / "rerun.json")
    assert current_table(resource) == data_table_name(row.id)


@uses_data_db
def test_orphans_are_listed_with_their_size_and_dropped_only_from_a_reviewed_report(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    owned = add_resource("cases.csv", "districts_v1.csv")
    legacy_row(owned, SHORT_LEGACY)
    legacy_table(SHORT_LEGACY, [("Kamrup", 10)])
    legacy_table("forgotten-table_1", [("Kamrup", 1)])
    legacy_table("forgotten-table_2", [("Kamrup", 2)])
    old_build = (datetime.now(dt_timezone.utc) - timedelta(hours=2)).isoformat()
    young_build = datetime.now(dt_timezone.utc).isoformat()
    frame = pd.DataFrame({"a": [1]})
    build_data_table("rdt_old_orphan", frame, json.dumps({"built_at": old_build}))
    build_data_table("rdt_in_flight", frame, json.dumps({"built_at": young_build}))

    run_command(report=tmp_path / "dry.json")
    orphans = read_report(tmp_path / "dry.json")["orphans"]
    assert sorted(o["name"] for o in orphans) == [
        "forgotten-table_1",
        "forgotten-table_2",
        "rdt_old_orphan",
    ]
    assert all(o["size_bytes"] > 0 for o in orphans)

    # Without a reviewed report nothing is dropped.
    with pytest.raises(CommandError, match="--from-report"):
        run_command("--apply", "--drop-orphans", report=tmp_path / "x.json")
    assert "forgotten-table_1" in tables.names()

    # Since the review, a row started using forgotten-table_2, and a new orphan appeared.
    late = add_resource("late.csv", "districts_v1.csv")
    legacy_row(late, "forgotten-table_2")
    legacy_table("not-reviewed", [("Kamrup", 3)])

    run_command(
        "--apply",
        "--drop-orphans",
        "--from-report",
        str(tmp_path / "dry.json"),
        report=tmp_path / "drop.json",
    )

    assert sorted(read_report(tmp_path / "drop.json")["orphans_dropped"]) == [
        "forgotten-table_1",
        "rdt_old_orphan",
    ]
    remaining = tables.names()
    assert "forgotten-table_1" not in remaining and "rdt_old_orphan" not in remaining
    # The late row's table was renamed by the same run, not dropped.
    assert current_table(late).startswith("rdt_")
    assert {current_table(late), "not-reviewed", "rdt_in_flight"} <= set(remaining)


@uses_data_db
def test_a_second_apply_after_completion_has_nothing_to_do(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    legacy_row(resource, SHORT_LEGACY)
    legacy_table(SHORT_LEGACY, [("Kamrup", 10)])
    run_command("--apply", report=tmp_path / "first.json")
    names_after_first = tables.names()

    output = run_command("--apply", report=tmp_path / "second.json")

    assert "nothing to do" in output
    assert tables.names() == names_after_first
    assert outcomes(read_report(tmp_path / "second.json")) == {
        data_table_name(ResourceDataTable.objects.get(resource=resource).id): "already_migrated"
    }


@uses_data_db
def test_rebuilds_list_the_access_models_whose_column_choices_reset(
    add_resource: Any, dataset: Any, tmp_path: Path
) -> None:
    resource = add_resource("first.csv", "districts_v1.csv")
    legacy_row(resource, LONG_FIRST)
    legacy_table(LONG_FIRST, WRONG_ROWS)
    access_model = AccessModel.objects.create(name="Partners", dataset=dataset)
    AccessModelResource.objects.create(access_model=access_model, resource=resource)

    run_command(report=tmp_path / "dry.json")

    assert read_report(tmp_path / "dry.json")["access_models_touched"] == [str(access_model.id)]


@uses_data_db
def test_the_command_refuses_when_the_data_database_is_the_main_database(
    tmp_path: Path,
) -> None:
    data = connections["data_db"].settings_dict
    same = {"HOST": data["HOST"], "PORT": data["PORT"], "NAME": data["NAME"]}
    with patch.dict(connections["default"].settings_dict, same):
        with pytest.raises(CommandError, match="main database"):
            run_command(report=tmp_path / "x.json")
    assert not (tmp_path / "x.json").exists()


@uses_data_db
def test_the_command_refuses_when_the_data_database_holds_django_tables(
    tables: Any, tmp_path: Path
) -> None:
    with connections["data_db"].cursor() as cursor:
        cursor.execute("CREATE TABLE django_migrations (id int)")
    legacy_table("forgotten-table", [("Kamrup", 1)])

    with pytest.raises(CommandError, match="django_migrations"):
        run_command("--apply", report=tmp_path / "x.json")
    assert "forgotten-table" in tables.names()


@uses_data_db
def test_a_dry_run_shows_what_apply_will_do_with_each_long_table(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    alone = add_resource("alone.csv", "districts_v1.csv")
    first = add_resource("first.csv", "districts_v1.csv")
    second = add_resource("second.csv", "districts_v2.csv")
    lonely_name = "x" * 70
    legacy_row(alone, lonely_name)
    legacy_table(lonely_name, WRONG_ROWS)
    legacy_row(first, LONG_FIRST)
    legacy_row(second, LONG_SECOND)
    legacy_table(LONG_SECOND, [("Kamrup", 11)])
    remove_stored_file(alone)
    remove_stored_file(first)

    run_command(report=tmp_path / "dry.json")

    report = read_report(tmp_path / "dry.json")
    assert outcomes(report) == {
        lonely_name: "planned_unverified_rename",
        LONG_FIRST: "planned_missing_file",
        LONG_SECOND: "planned_rebuild",
    }
    assert {e["table_name"]: e["shared"] for e in report["rows"]} == {
        lonely_name: False,
        LONG_FIRST: True,
        LONG_SECOND: True,
    }
    assert report["shared_groups"] == 1
    assert [e["table_name"] for e in report["needs_manual_fix"]] == [LONG_FIRST]
    assert current_table(alone) == lonely_name  # a dry run changes nothing


@uses_data_db
def test_a_long_table_whose_file_can_no_longer_become_a_table_is_kept_and_marked(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    alone = add_resource("alone.csv", "districts_v1.csv")
    first = add_resource("first.csv", "districts_v1.csv")
    second = add_resource("second.csv", "districts_v2.csv")
    lonely_name = "x" * 70
    legacy_row(alone, lonely_name)
    legacy_table(lonely_name, WRONG_ROWS)
    legacy_row(first, LONG_FIRST)
    legacy_row(second, LONG_SECOND)
    legacy_table(LONG_SECOND, [("Kamrup", 11)])
    for resource in (alone, first):  # later replaced by a PDF, which gets no table
        resource.resourcefiledetails.format = "pdf"
        resource.resourcefiledetails.save()

    run_command("--apply", report=tmp_path / "apply.json")
    assert outcomes(read_report(tmp_path / "apply.json")) == {
        lonely_name: "unverified",
        LONG_FIRST: "not_indexable",  # still shared at planning time: left alone
        LONG_SECOND: "rebuilt",
    }

    # With its sharer gone, the left-behind row is now alone, so a rerun marks it too.
    run_command("--apply", report=tmp_path / "rerun.json")
    assert outcomes(read_report(tmp_path / "rerun.json"))[LONG_FIRST] == "unverified"

    output = run_command("--apply", report=tmp_path / "last.json")
    assert "nothing to do" in output
    assert len(read_report(tmp_path / "last.json")["unverified_tables"]) == 2


@uses_data_db
def test_rebuilds_read_files_with_no_time_limit(add_resource: Any, tmp_path: Path) -> None:
    resource = add_resource("first.csv", "districts_v1.csv")
    legacy_row(resource, LONG_FIRST)
    legacy_table(LONG_FIRST, WRONG_ROWS)

    with patch(
        "api.utils.data_table_migration.index_resource_data", return_value=MagicMock()
    ) as index:
        run_command("--apply", report=tmp_path / "apply.json")

    index.assert_called_once()
    assert index.call_args.kwargs == {"load_timeout": None}


@uses_data_db
def test_a_row_whose_table_is_gone_is_reindexed_or_left_for_a_person(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    has_file = add_resource("has-file.csv", "districts_v1.csv")
    no_file = add_resource("no-file.csv", "districts_v1.csv")
    gone = ResourceDataTable.objects.create(resource=has_file)  # rdt_ name, table never built
    ResourceDataTable.objects.create(resource=no_file)
    remove_stored_file(no_file)

    output = run_command("--apply", report=tmp_path / "apply.json")

    report = read_report(tmp_path / "apply.json")
    assert sorted(e["outcome"] for e in report["rows"]) == ["missing_file", "reindexed"]
    assert current_table(has_file) != gone.table_name
    assert len(tables.rows(current_table(has_file))) == 3
    assert "nothing to do" not in output
    assert "nothing to do" in run_command("--apply", report=tmp_path / "rerun.json")


@uses_data_db
def test_resource_id_limits_the_run_to_that_resource(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    target = add_resource("target.csv", "districts_v1.csv")
    other = add_resource("other.csv", "districts_v1.csv")
    legacy_row(target, SHORT_LEGACY)
    legacy_table(SHORT_LEGACY, [("Kamrup", 10)])
    legacy_row(other, "other-legacy-table")
    legacy_table("other-legacy-table", [("Kamrup", 1)])

    run_command("--apply", "--resource-id", str(target.id), report=tmp_path / "one.json")

    assert current_table(target).startswith("rdt_")
    assert current_table(other) == "other-legacy-table"


@uses_data_db
def test_a_rename_backs_off_when_an_upload_replaced_the_row_after_planning(
    add_resource: Any, tables: Any
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    row = legacy_row(resource, SHORT_LEGACY)
    legacy_table(SHORT_LEGACY, [("Kamrup", 10)])
    planned = DataTableRow(row.id, resource.id, SHORT_LEGACY, row.created)
    ResourceDataTable.objects.filter(pk=row.pk).update(table_name="rdt_" + "f" * 32)

    assert rename_legacy_table(planned) == "changed"
    assert SHORT_LEGACY in tables.names()


@uses_data_db
def test_a_bad_reviewed_report_stops_the_run_before_any_change(
    add_resource: Any, tables: Any, tmp_path: Path
) -> None:
    resource = add_resource("cases.csv", "districts_v1.csv")
    legacy_row(resource, SHORT_LEGACY)
    legacy_table(SHORT_LEGACY, [("Kamrup", 10)])
    (tmp_path / "edited.json").write_text('{"orphans": [{"name": "a"},]}')  # trailing comma

    for reviewed in ("missing.json", "edited.json"):
        with pytest.raises(CommandError, match="reviewed report"):
            run_command(
                "--apply",
                "--drop-orphans",
                "--from-report",
                str(tmp_path / reviewed),
                report=tmp_path / "out.json",
            )

    assert current_table(resource) == SHORT_LEGACY


@uses_data_db
def test_the_report_may_not_overwrite_the_reviewed_report(tmp_path: Path) -> None:
    run_command(report=tmp_path / "dry.json")
    reviewed = (tmp_path / "dry.json").read_text()

    with pytest.raises(CommandError, match="overwrite"):
        run_command(
            "--apply",
            "--drop-orphans",
            "--from-report",
            str(tmp_path / "dry.json"),
            report=tmp_path / "dry.json",
        )

    assert (tmp_path / "dry.json").read_text() == reviewed


# --- Layer 2: orphan rules ---------------------------------------------------

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=dt_timezone.utc)


def table(name: str, built_minutes_ago: Any = None) -> DataDbTable:
    comment = None
    if built_minutes_ago is not None:
        built_at = (NOW - timedelta(minutes=built_minutes_ago)).isoformat()
        comment = json.dumps({"built_at": built_at})
    return DataDbTable(name=name, size_bytes=8192, comment=comment)


def test_orphans_never_include_django_tables_rows_tables_or_fresh_builds() -> None:
    row_id = __import__("uuid").uuid4()
    rows = [
        DataTableRow(row_id=row_id, resource_id=row_id, table_name=LONG_FIRST, created=NOW),
    ]
    candidates = [
        table("resource_data_table"),  # a Django model's table
        table("django_migrations"),
        table(SHARED_PREFIX),  # the row's (cut) table
        table(data_table_name(row_id)),  # the row's renamed table, row not yet updated
        table("rdt_" + "a" * 32, built_minutes_ago=5),  # an upload still switching
        table("rdt_" + "b" * 32, built_minutes_ago=90),
        table("rdt_" + "c" * 32),  # no readable build time
        table("forgotten-table"),
    ]

    names = [t.name for t in find_orphans(rows, candidates, now=NOW)]

    assert names == ["rdt_" + "b" * 32, "rdt_" + "c" * 32, "forgotten-table"]


# --- Layer 3: the command's flow (helpers mocked) ----------------------------

COMMAND = "api.management.commands.migrate_data_table_names"


@pytest.fixture
def command_helpers() -> Any:
    parent = MagicMock(unsafe=True)  # one helper's name starts with "assert"
    names = [
        "assert_data_db_is_separate",
        "read_data_table_rows",
        "list_data_db_tables",
        "plan_table_migration",
        "point_row_at_its_table",
        "rename_legacy_table",
        "rebuild_from_file",
        "rebuild_decision",
        "reindex_decision",
        "reindex_missing_table",
        "find_unverified",
        "access_models_touched",
        "read_reviewed_orphans",
        "find_orphans",
        "drop_reviewed_orphans",
        "write_report",
    ]
    patchers = [patch(f"{COMMAND}.{name}", getattr(parent, name)) for name in names]
    for p in patchers:
        p.start()
    row = lambda name: DataTableRow(  # noqa: E731
        row_id=name, resource_id=name, table_name=name, created=NOW
    )
    plan = MagicMock()
    plan.already_migrated = []
    plan.row_updates = [row("crashed")]
    plan.renames = [row("short")]
    plan.rebuilds = [(row("long_old"), False), (row("long_new"), True)]
    plan.missing_tables = [row("missing")]
    plan.orphans = []
    plan.shared_groups = 1
    parent.plan_table_migration.return_value = plan
    parent.point_row_at_its_table.return_value = "row_updated"
    parent.rename_legacy_table.return_value = "renamed"
    parent.rebuild_from_file.return_value = "rebuilt"
    parent.reindex_missing_table.return_value = "reindexed"
    parent.rebuild_decision.return_value = "rebuild"
    parent.reindex_decision.return_value = "reindex"
    parent.find_unverified.return_value = []
    parent.access_models_touched.return_value = []
    parent.drop_reviewed_orphans.return_value = []
    yield parent
    for p in patchers:
        p.stop()


def top_level_calls(parent: MagicMock) -> List[str]:
    return [c[0] for c in parent.mock_calls if c[0] and "." not in c[0] and "(" not in c[0]]


def test_a_dry_run_checks_safety_first_and_changes_nothing(
    command_helpers: MagicMock, tmp_path: Path
) -> None:
    call_command(
        "migrate_data_table_names", "--report", str(tmp_path / "r.json"), stdout=StringIO()
    )

    calls = top_level_calls(command_helpers)
    assert calls[0] == "assert_data_db_is_separate"
    assert "write_report" in calls
    for action in [
        "point_row_at_its_table",
        "rename_legacy_table",
        "rebuild_from_file",
        "reindex_missing_table",
        "drop_reviewed_orphans",
    ]:
        assert action not in calls


def test_apply_fixes_crashed_rows_then_renames_then_rebuilds_in_order(
    command_helpers: MagicMock, tmp_path: Path
) -> None:
    call_command(
        "migrate_data_table_names",
        "--apply",
        "--report",
        str(tmp_path / "r.json"),
        stdout=StringIO(),
    )

    actions = [
        (c[0], c.args[0].table_name)
        for c in command_helpers.mock_calls
        if c[0]
        in {
            "point_row_at_its_table",
            "rename_legacy_table",
            "rebuild_from_file",
            "reindex_missing_table",
        }
    ]
    assert actions == [
        ("point_row_at_its_table", "crashed"),
        ("rename_legacy_table", "short"),
        ("rebuild_from_file", "long_old"),
        ("rebuild_from_file", "long_new"),
        ("reindex_missing_table", "missing"),
    ]
    command_helpers.drop_reviewed_orphans.assert_not_called()


def test_the_command_stops_before_reading_anything_when_safety_fails(
    command_helpers: MagicMock, tmp_path: Path
) -> None:
    from api.utils.data_tables import DataDbNotSeparate

    command_helpers.assert_data_db_is_separate.side_effect = DataDbNotSeparate("same database")

    with pytest.raises(CommandError):
        call_command("migrate_data_table_names", "--apply", "--report", str(tmp_path / "r.json"))

    assert top_level_calls(command_helpers) == ["assert_data_db_is_separate"]


def test_orphans_are_dropped_only_with_apply_and_a_reviewed_report(
    command_helpers: MagicMock, tmp_path: Path
) -> None:
    with pytest.raises(CommandError):
        call_command("migrate_data_table_names", "--drop-orphans", "--from-report", "r.json")
    command_helpers.drop_reviewed_orphans.assert_not_called()

    command_helpers.read_reviewed_orphans.return_value = {"forgotten-table"}
    call_command(
        "migrate_data_table_names",
        "--apply",
        "--drop-orphans",
        "--from-report",
        str(tmp_path / "reviewed.json"),
        "--report",
        str(tmp_path / "r.json"),
        stdout=StringIO(),
    )
    command_helpers.read_reviewed_orphans.assert_called_once_with(str(tmp_path / "reviewed.json"))
    command_helpers.drop_reviewed_orphans.assert_called_once_with(
        {"forgotten-table"}, command_helpers.find_orphans.return_value
    )
