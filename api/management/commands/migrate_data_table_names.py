"""Move existing data tables to per-upload names, and list the tables nothing uses.

    python manage.py migrate_data_table_names            # dry run: write a report, change nothing
    python manage.py migrate_data_table_names --apply    # rename, rebuild, fix rows
    python manage.py migrate_data_table_names --apply --drop-orphans --from-report <reviewed.json>

    --resource-id <uuid>   act on one resource only
    --report <path>        where to write the JSON report (default: a timestamped file here)

Short old names are renamed in place; long ones (which may hold another
resource's data) are rebuilt from each resource's own file. A long one whose
file is missing or unusable is renamed and marked "unverified" (listed in
every report until the resource is re-uploaded), or left alone if another row
shares it. A dry run checks the files too, so it shows what --apply will do.
Safe to rerun: each run picks up whatever is left ("nothing to do" once only
rows needing a person remain), and doubles as an orphan audit.

Docs (runbook, failure model): ../../utils/data_indexing_architecture.md
"""

from typing import Any, Dict, List

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from api.utils.data_table_migration import (
    access_models_touched,
    build_report,
    drop_reviewed_orphans,
    find_orphans,
    find_unverified,
    nothing_left_to_do,
    plan_table_migration,
    point_row_at_its_table,
    read_data_table_rows,
    read_reviewed_orphans,
    rebuild_decision,
    rebuild_from_file,
    record_outcome,
    reindex_decision,
    reindex_missing_table,
    rename_legacy_table,
    same_file,
    summary_lines,
    write_report,
)
from api.utils.data_tables import (
    DataDbNotSeparate,
    assert_data_db_is_separate,
    list_data_db_tables,
)


class Command(BaseCommand):
    help = "Move data tables to per-upload rdt_<id> names; list (and drop reviewed) orphans."

    def add_arguments(self, parser: CommandParser) -> None:
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Report only (the default).")
        mode.add_argument("--apply", action="store_true", help="Rename, rebuild and fix rows.")
        parser.add_argument(
            "--drop-orphans",
            action="store_true",
            help="With --apply: drop orphans listed in --from-report that are still orphans.",
        )
        parser.add_argument("--from-report", help="A dry-run report someone reviewed.")
        parser.add_argument("--resource-id", help="Act on this resource only.")
        parser.add_argument("--report", help="Where to write this run's JSON report.")

    def handle(self, *args: Any, **options: Any) -> None:
        apply, drop_orphans, from_report = (
            options["apply"],
            options["drop_orphans"],
            options["from_report"],
        )
        mode = "apply" if apply else "dry-run"
        now = timezone.now()
        report_path = options["report"] or f"data_table_migration_{now:%Y%m%dT%H%M%SZ}.json"

        # Orphans are dropped only by an applying run, and only from a reviewed report.
        if drop_orphans and not (apply and from_report):
            raise CommandError("--drop-orphans needs --apply and --from-report <reviewed report>")
        if from_report and same_file(report_path, from_report):
            raise CommandError("--report would overwrite the reviewed --from-report file")

        # Never touch anything if the data database might be the main database.
        try:
            assert_data_db_is_separate()
        except DataDbNotSeparate as error:
            raise CommandError(f"Refusing to run: {error}") from error

        # Read the reviewed orphan list now, so a bad file stops the run before any change.
        reviewed = read_reviewed_orphans(from_report) if drop_orphans else set()

        # Write an in-progress report first: the path works, and a run that dies leaves a trace.
        write_report(report_path, build_report(mode, now, status="in_progress"))

        # Read every row and every data table, and work out what each row needs.
        plan = plan_table_migration(
            read_data_table_rows(), list_data_db_tables(), now, resource_id=options["resource_id"]
        )
        entries: List[Dict[str, Any]] = [
            record_outcome(row, "none", "already_migrated") for row in plan.already_migrated
        ]

        if apply:
            # Finish renames a crashed run left half done: just point the row at its table.
            for row in plan.row_updates:
                entries.append(record_outcome(row, "row_update", point_row_at_its_table(row)))

            # Rename short old tables in place; they can't have collided.
            for row in plan.renames:
                entries.append(record_outcome(row, "rename", rename_legacy_table(row)))

            # Rebuild long old tables from each resource's own file, oldest first.
            for row, shared in plan.rebuilds:
                outcome = rebuild_from_file(row, shared)
                entries.append(record_outcome(row, "rebuild", outcome, shared=shared))

            # Re-index rows whose table is gone, from their file.
            for row in plan.missing_tables:
                entries.append(record_outcome(row, "reindex", reindex_missing_table(row)))
        else:
            # A dry run changes nothing, but checks each stored file so the report shows
            # what --apply would really do (rebuild, unverified rename, or leave for a person).
            for row in plan.row_updates:
                entries.append(record_outcome(row, "row_update", "planned_row_update"))
            for row in plan.renames:
                entries.append(record_outcome(row, "rename", "planned_rename"))
            for row, shared in plan.rebuilds:
                decision = rebuild_decision(row, shared)
                entries.append(record_outcome(row, "rebuild", f"planned_{decision}", shared=shared))
            for row in plan.missing_tables:
                entries.append(record_outcome(row, "reindex", f"planned_{reindex_decision(row)}"))

        # Rebuilt resources get new column rows, which resets access models' column choices.
        touched = access_models_touched(
            [row.resource_id for row, _ in plan.rebuilds]
            + [row.resource_id for row in plan.missing_tables]
        )

        dropped: List[str] = []
        if drop_orphans:
            # Drop the reviewed orphans that are still orphans right now.
            current = find_orphans(read_data_table_rows(), list_data_db_tables(), timezone.now())
            dropped = drop_reviewed_orphans(reviewed, current)

        # List every table still marked unverified, from this run or any earlier one.
        unverified = find_unverified(read_data_table_rows(), list_data_db_tables())

        # Write the full report and print the summary.
        report = build_report(
            mode,
            now,
            entries,
            plan.orphans,
            dropped,
            touched,
            unverified,
            plan.shared_groups,
        )
        write_report(report_path, report)
        if nothing_left_to_do(entries):
            self.stdout.write("nothing to do")
        for line in summary_lines(report, report_path):
            self.stdout.write(line)
