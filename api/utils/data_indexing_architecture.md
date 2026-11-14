# Data index — per-upload data tables

> Backend only. Related: [`docs/dataset_data_api.md`](../../docs/dataset_data_api.md) (the public data API that reads these tables). Plan: `plans/claude/data-index-table-names.md`.

## Overview

Every tabular resource file (csv, xls, xlsx, ods, parquet, feather, json, tsv) is copied into a table of its own in the separate `data_db` Postgres database. Previews, row counts, the column list, the data API (`/api/resources/<id>/data/`, `/api/datasets/<id>/data/`) and chart queries read those tables. A resource's `ResourceDataTable` row (main database) records which table is its own; every reader looks the table up from that row, never from a name rule.

This feature makes each upload's table **unique and safely replaced**:

- **Names come from the upload's own row id:** `rdt_<32 hex of the ResourceDataTable id>`, 36 characters. They never collide and never change when a resource or dataset is renamed.
- **Re-uploads build first, then switch, then drop.** The new table is built completely, one main-database commit points the resource at it, and the old table is dropped only after that commit. Readers see the complete old data, then the complete new data. A failed re-upload leaves the old data exactly as it was.
- **Deletes free storage.** Deleting a resource, a dataset (by cascade), or a row in the admin drops the table once the delete commits. A rolled-back delete keeps it.
- **Existing tables are migrated by a one-off command** (`migrate_data_table_names`). Its runbook is below.

Why it was needed: names used to be `slug(resource name)[:50]_slug(dataset title)[:50]_<8 hex>`, up to 110 characters. Postgres keeps only the first 63 bytes of any name, so the id suffix was usually cut off and two resources with long, similar names shared one physical table. A re-upload of one replaced the other's data, and the other's preview, charts and data API served the wrong numbers. Re-uploads also dropped the old table before building the new one: readers saw empty or half-written data for a few seconds, a failed re-upload lost the data for good, and deletes never dropped anything.

## Submodule map

| Submodule | Trigger | Code |
|---|---|---|
| Upload / re-index flow | GraphQL `createFileResources`, `updateFileResource` (with a file), `resetFileResourceSchema`, `updateFileResourceSchema` (when a column format changes); `python manage.py update_dataindex` | `index_resource_data` in `api/utils/data_indexing.py`; helpers in `api/utils/data_tables.py` |
| Table names | used by the model and the flow | `api/utils/data_table_names.py` |
| Delete clean-up | `post_delete` of any `ResourceDataTable` row (re-upload, resource/dataset delete, admin delete) | `api/signals/data_table_signals.py` → `drop_data_table_if_unshared` |
| Readers | GraphQL resource fields (preview, row count), data API views, chart generator | `get_row_count`, `get_preview_data`, `get_resource_columns`, `fetch_resource_data`, `query_resource_data` in `api/utils/data_indexing.py` (unchanged) |
| Migration of existing tables | `python manage.py migrate_data_table_names` (one-off, operator-run) | `api/management/commands/migrate_data_table_names.py`; helpers in `api/utils/data_table_migration.py` |

---

## Submodule: Upload / re-index flow

### Trigger
`index_resource_data(resource, load_timeout=60)` is called synchronously by the resource file mutations in `api/schema/resource_schema.py` (none of them runs inside a transaction), by `update_dataindex` per resource, and by the migration command for rebuilds (with `load_timeout=None`).

### Business use case
A publisher uploads or replaces a tabular file. Visitors then preview it, chart it and query it through the data API. They must never see another resource's data, an empty table mid-replace, or lose the old data because a new file was bad.

### Flow (English)
1. **Refuse inside an outer transaction.** If the main database is already in an atomic block, log `data_index_refused_inside_transaction` and return None. Inside someone else's transaction, "committed" would only mean a savepoint was released, and a later rollback would leave a switched table pointing nowhere.
2. **Check the file.** The resource must have a stored file in an indexed format; otherwise return None. Nothing is built.
3. **Load the file** into a frame, and note which stored file it was (storage name + `sha256`). Loading is limited to 60 s where the platform allows it: SIGALRM works only in a process's main thread, so management commands get the limit and web worker threads never have. Column names are cleaned: double quotes removed, line breaks and tabs become spaces, and names that then collide get `_1`, `_2`… An unreadable file, a timeout or an empty frame returns None.
4. **Make this upload's row in memory.** A new `ResourceDataTable` with its UUID, so its table name `rdt_<hex>` is known before anything is saved.
5. **Build the new table** in one `data_db` transaction: create it, copy the rows in through a temporary table (`ON COMMIT DROP`), and store a JSON comment (resource id and name, dataset title, `built_at`). A failure, such as a value out of range mid-copy, rolls the whole table back, and the old row and table are untouched.
6. **Switch, in one main-database transaction:**
   1. lock the resource row (`select_for_update`), so two uploads of one resource switch one after the other;
   2. re-read the stored file's identity, and if a newer file was saved while this one was building, back off (`NewerFileSaved`), because the newest file wins;
   3. delete the old `ResourceDataTable` row, if any. Its delete receiver schedules the old table's drop for after the commit;
   4. save the new row, carrying over the old row's `created` (see "Dataset default table" below);
   5. rebuild the `ResourceSchema` column rows (descriptions people wrote are kept by column name). Errors escape, and a header longer than the 255-character `field_name` is refused up front.
7. **Confirm the switch.** It counts only if the new row exists after the transaction.
8. **`finally`: drop this build's table unless step 7 confirmed the switch.** That covers a failed build, a failed switch, a newer file, a missing row, and even `KeyboardInterrupt`. Before dropping, it checks the database: if the new row was saved after all (a command stopped with Ctrl+C while the old table's after-commit drop waited for a reader, or a commit that went through but reported an error), the table is the resource's live data and stays. If the check itself fails, the table is left for the orphan audit.
9. After the commit, the receiver drops the old table (see Delete clean-up).

Returns the new `ResourceDataTable`, or None when the resource was not switched (each reason logged).

**Why the switch lets errors escape.** The old column rebuild caught each column's error. Inside an atomic block a database error marks the whole block for rollback, so one bad header silently rolled the switch back while the upload still looked successful.

**Why the newest file wins.** Each upload request saves its own file before indexing it. Without the re-check, a slow build of an older file could switch in last: the download would serve one file while previews, charts and the data API served another.

**Dataset default table.** `GET /api/datasets/<id>/data/` without `resource_id` serves the dataset's data table with the oldest `created`. The new row inherits the old row's `created`, so replacing a file never moves a dataset's default to another resource. The migration doesn't reshuffle defaults either.

### Helpers (`api/utils/data_tables.py`, Tier 2 unless noted)
- `is_inside_transaction() -> bool`: whether the main DB is in an atomic block.
- `has_indexable_file(resource) -> bool`: has a stored file whose format is in `INDEXED_FORMATS`; logs why not.
- `load_resource_frame(resource, timeout=60) -> LoadedFile | None`: frame plus `FileIdentity(name, sha256)`; None (logged) when unreadable, too slow, or empty. Depends on Tier 1 `local_copy`, `load_tabular_data` (`api/utils/file_utils.py`).
- `stored_file_identity(resource) -> FileIdentity | None`: the current file, read fresh from the database.
- `new_data_table_row(resource) -> ResourceDataTable`: unsaved, named `rdt_<own id>`.
- `describe_data_table(resource, built_at, unverified=False) -> str`: the table comment (JSON). `unverified` is used only by the migration.
- `build_data_table(table_name, frame, comment)`: one `data_db` transaction. Raises on failure, leaving nothing behind. Names via `sql.Identifier`, comment via `sql.Literal`.
- `lock_resource(resource)`: `select_for_update` on the resource row (no-op on SQLite).
- `retire_data_table_row(resource) -> datetime | None`: deletes the current row, returns its `created`.
- `save_data_table_row(row, created)`: inserts, then sets `created` with a queryset update (it's `auto_now_add`).
- `rebuild_resource_schema(resource, frame)`: replaces column rows. Raises `ValueError("column N header is longer than 255 characters")` and lets DB errors escape.
- `data_table_row_exists(row_id) -> bool`.
- `drop_unswitched_table(row)`: the flow's clean-up. It drops the build's table only if its row isn't saved, and leaves it when the check fails. Never raises.
- `drop_data_table(name) -> bool`: `DROP TABLE IF EXISTS` with `SET LOCAL lock_timeout = '5s'`. Never raises: a failure is logged (`data_table_drop_failed`) and the table is left as an orphan for the migration command to report.
- `error_fields(error) -> dict`: `error_type`, Postgres `error_code`, and `where` (innermost frame in `api/`). **Never the message**, because COPY errors quote the offending cell value.
- `get_sql_type(dtype) -> str`: BIGINT / DOUBLE PRECISION / TIMESTAMP / BOOLEAN / TEXT (moved here; still importable from `data_indexing`, as are `DATA_DB` and `INDEXED_FORMATS`).

`api/utils/data_table_names.py` (no model imports, because the model uses it):
- `data_table_name(row_id) -> "rdt_" + hex`.
- `physical_table_name(name) -> str`: the first 63 bytes, never half a character (what Postgres stores).
- `may_share_physical_table(name) -> bool`: only names of ≥ 60 bytes can be the cut of a longer one.

### Model rule
`ResourceDataTable.save()` fills a blank `table_name` with `data_table_name(self.id)`. Existing rows keep their stored names. Nothing else generates names. Rolling the code back is safe: old code only generates a name when the field is blank, and every reader uses the stored name.

---

## Submodule: Delete clean-up

### Trigger
`post_delete` with `sender=ResourceDataTable`. Django sends it for every row in a cascade or a queryset delete, because a receiver is connected (no fast delete). That covers re-upload (`retire_data_table_row`), `deleteFileResource`, `deleteDataset`, admin deletes of a row, resource or dataset, and the migration's rebuilds.

### Flow (English)
1. The receiver schedules `drop_data_table_if_unshared(table_name, row_id)` with `transaction.on_commit(..., using=<signal's db>, robust=True)`.
2. After the commit, the drop helper checks whether another row still maps to the same physical table. This is possible only for old long names; `rdt_` names skip the check.
   1. If one does, it logs `data_table_drop_skipped_shared` and keeps the table.
   2. Otherwise it drops the table (5 s lock timeout). Any failure is logged and swallowed.

A rolled-back delete never runs the callback, so its data is kept.

**Registration.** The module is imported by `api/signals/__init__.py`. A test checks the receiver is connected in a fresh interpreter, because `collaborative_signals.py` once shipped without being imported and never ran.

**Lock order.** A switch locks the resource, then its data-table row. A resource delete locks the rows, then the resource. A switch and a delete of the same resource at the same moment can therefore deadlock. Postgres aborts one of them, and nothing is lost: the aborted switch drops its own table, and the aborted delete leaves everything in place.

---

## Submodule: Readers (unchanged)
`get_row_count`, `get_preview_data`, `get_resource_columns` (falls back to `information_schema` by table name when there are no column rows), `fetch_resource_data` (data API; column names via `_column_ident`, which doubles `%`), and `query_resource_data` (charts; `{{table}}` replaced by the quoted table name). They all look up `ResourceDataTable` per call and work unchanged on `rdt_` tables. A reader that fetched the old row just before a switch can hit "relation does not exist" once the old table is dropped. It then takes its existing error path (None / 0 / the data API's 500); it never gets the new file's rows under the old row. Readers still compose the table name with f-strings; `rdt_` names are safe in that position.

---

## Submodule: Migration of existing tables — `migrate_data_table_names`

### Trigger
Operator-run, once after deploy (and safe to rerun any time as an orphan audit).

### Business use case
Move every existing table to an `rdt_` name and repair tables two resources were sharing. Then list, and after review drop, tables nothing uses (left behind by deletes from before this feature).

### Flow (English)
1. Check the options. `--drop-orphans` needs `--apply` and `--from-report`, and `--report` must not name the reviewed file.
2. **Safety:** refuse if `data_db` and the main database name the same host, port and database, or if `data_db` holds `django_migrations` or any Django model's table. Either would make every application table look like an orphan.
3. Read the reviewed orphan list now, if dropping. A missing or malformed file stops the run before any change.
4. Write an "in progress" report. This proves the path is writable, and a run that dies leaves a trace.
5. Read every row (oldest first) and every `data_db` table (size and comment), and sort each row (limited to `--resource-id` if given):
   - **already migrated**: `rdt_<own id>` exists;
   - **row update**: a crashed earlier run renamed the table but didn't update the row (the old name is gone, `rdt_<own id>` exists);
   - **rename**: an old name of ≤ 63 bytes. It can't have collided;
   - **rebuild**: an old name of > 63 bytes, whether one row or several point at the physical table. It may already hold another resource's data, so it is never just renamed while its file is usable. Each rebuild carries whether the table is shared;
   - **missing table**: neither name exists.
6. **Dry run (the default):** change nothing, but check each rebuild's and missing table's stored file, and record the planned outcome:
   - `planned_rebuild`;
   - `planned_unverified_rename`: the file is missing or unusable and the table is not shared;
   - `planned_missing_file` / `planned_not_indexable`: the table is shared, so it is left for a person;
   - `planned_reindex`.
7. **`--apply`**, in this order:
   1. **Row updates.**
   2. **Renames:** in a main-DB transaction, lock the resource and re-check that the row still has its old name (otherwise `changed`). Then, in `data_db`, `SET LOCAL lock_timeout = '2s'`, rename the table and set its comment. Update the row last. A lock timeout gives `skipped_lock`, and a rerun finishes it.
   3. **Rebuilds:** oldest first, through `index_resource_data(resource, load_timeout=None)`. The old row's delete receiver keeps a shared table until its last row has moved.
      - If the file is missing or can no longer become a table (for example, later replaced by a PDF) and no other row uses the table, it is renamed and **marked `"unverified": true` in its comment** (`unverified`).
      - If the table is shared, it is left (`missing_file` / `not_indexable`). Once its sharers have moved, the next run finds it alone and marks it unverified.
   4. **Missing tables:** re-indexed from the file, or `missing_file` / `not_indexable`.
8. **`--drop-orphans`:** recompute orphans now, and drop only those that are both in the reviewed report and still orphans.
9. Write the full report and print the summary. Every row's outcome is also logged as it happens (`data_table_migration_row`). "nothing to do" is printed when no row needs a rerun: every row is migrated, or needs a person (missing or unusable file).

**Orphans:**
- **Never orphans:** a Django model's table, any row's physical table or `rdt_<row id>`, and an `rdt_` table whose comment says it was built under an hour ago (its upload may still be switching).
- **Listed:** `rdt_` tables without a readable build time, because every table the new code builds has a comment written in the same transaction as its creation.
- Each listed orphan carries its size and comment.

**Unverified tables** are listed in every report (`unverified_tables`), dry run or apply, until the resource is re-uploaded (the new table has no mark). They may hold another resource's data. Restore the resource's file and re-upload it, or check the data by hand.

**Report** (JSON, default `data_table_migration_<UTC timestamp>.json` in the working directory):
- `mode`, `status`;
- `counts` by outcome and `shared_groups`;
- `rows` (ids, table name, action, outcome, `shared`);
- `needs_manual_fix`;
- `unverified_tables`;
- `orphans` (name, size, comment), `orphans_dropped`;
- `access_models_touched`: access models whose column choices are reset because the resource's column rows are recreated. This is existing re-upload behaviour.

No file contents or values appear in the report.

### Runbook
1. Deploy. New uploads use `rdt_` names from now on, and old names keep working.
2. Off-peak: `python manage.py migrate_data_table_names --report dry.json`. Review `counts`, `shared_groups`, `needs_manual_fix` (restore files first if you can), `unverified_tables` and `orphans`.
3. `python manage.py migrate_data_table_names --apply --report apply1.json`. Rerun until it prints "nothing to do".
   - `skipped_lock` and `failed` rows are retried.
   - A row that comes back `failed` on two runs in a row needs a person: its file is stored and in a supported format but won't load or switch (it doesn't parse, has only a header, or has a header over 255 characters). Find it under `rows` with outcome `failed`, using the resource id and the `data_index_failed` / `data_index_load_failed` log lines. Its old table keeps serving unmarked, and a long one may hold another resource's data.
   - A shared table whose file is missing is marked on the run after its sharers move.
4. At least an hour later: `python manage.py migrate_data_table_names --report orphans.json`. Review the orphan list and remove from the file any table you want kept.
5. `python manage.py migrate_data_table_names --apply --drop-orphans --from-report orphans.json --report drop.json`.
6. Follow up on `unverified_tables` and `needs_manual_fix` by hand.

Renames take an exclusive lock briefly and wait up to 2 s behind running reads. Rebuilds hold two copies of a table for a moment.

**Old naming schemes the command meets:**
- `resource_data_<32 hex>`: March–May 2025, 46 characters, so renamed.
- Raw `<resource name>-<dataset name or title>-<32 hex>`: May–July 2025. These can be mixed case, contain spaces or non-ASCII, and are usually over 63 bytes, so they are rebuilt.
- `slug(name)[:50]_slug(title)[:50]_<8 hex>`: from July 2025. Short ones are renamed and long ones rebuilt.

Short names of every scheme are unique, so they can't have collided.

### Helpers (`api/utils/data_table_migration.py`, plus `list_data_db_tables`, `django_table_names`, `assert_data_db_is_separate`, `table_built_at`, `table_is_unverified` in `data_tables.py`)
- `read_data_table_rows()`: every row, oldest first, as `DataTableRow(row_id, resource_id, table_name, created)`.
- `plan_table_migration(rows, tables, now, resource_id=None) -> MigrationPlan`: pure; the sorting above, plus `orphans` and `shared_groups`.
- `find_orphans(rows, tables, now)`: pure; the orphan rules.
- `file_problem(resource)`: `missing_file`, `not_indexable` or None. Storage errors are raised.
- `rebuild_decision(row, shared)` / `reindex_decision(row)`: what `--apply` will do (`check_failed` if the file check errors).
- `point_row_at_its_table`, `rename_legacy_table(row, unverified=False)`, `rebuild_from_file(row, shared)`, `reindex_missing_table(row)`: the actions. Each returns an outcome string and never raises.
- `find_unverified(rows, tables)`: rows whose table carries the mark.
- `access_models_touched(resource_ids)`, `read_reviewed_orphans(path)` (CommandError when unreadable), `same_file`, `drop_reviewed_orphans(reviewed, current)`, `record_outcome` (logs and returns the report line), `nothing_left_to_do`, `build_report`, `write_report`, `summary_lines`.

---

## Data model
- `ResourceDataTable` (`resource_data_table`): `id` UUID pk, `resource` one-to-one, `table_name` CharField(255) unique, `created`, `modified`. **No schema change and no migration file.** Only the generated value changed. `created` is now carried over on re-upload.
- `ResourceSchema`: rebuilt on every re-index (existing behaviour). `AccessModelResource.fields` (many-to-many to these rows) loses its selections whenever they are rebuilt, as before.
- `ResourceFileDetails.file` and `sha256` are read as the file identity (`sha256` is computed on save when the file changes).
- `data_db` tables: one per tabular resource, named `rdt_<row id hex>`, with a JSON comment: `resource_id`, `resource`, `dataset`, `built_at`, and `unverified` when the migration kept a table without a rebuild.
- No Elasticsearch documents are affected.

## Indexing & performance
- **Switch:** `Resource` by pk (`select_for_update`); `ResourceDataTable` by `resource_id` (one-to-one unique index); `ResourceFileDetails` by `resource_id` (unique).
- **Receiver guard:** `ResourceDataTable.table_name LIKE '<63-byte prefix>%'`, only for old names of ≥ 60 bytes (`rdt_` names skip it). This uses the unique btree on `table_name`, but may be a sequential scan on non-C collations. That's acceptable at one row per tabular resource (thousands).
- **Command:** one ordered read of `ResourceDataTable` (values only, iterator) and one `pg_class` catalogue query on `data_db`. Each is repeated once at the end, and once more when dropping orphans.
- **`data_db`:** no indexes added. Readers do full-table reads with existing timeouts.
- **Disk:** a re-upload briefly holds two copies of the table.
- No new user-facing query, so no pagination change.

## Security
- No new endpoint and no permission change. The file mutations keep their `ChangeResourcePermission` (edit rights on the dataset) and the data API keeps its existing check. If a user from another organization sends the same mutation, it is refused exactly as before (`tests/schema/test_resource_permissions.py`).
- Out of scope, and unchanged: the public row API serves rows of any PUBLISHED dataset regardless of `access_type`.
- All new SQL composes table names with `sql.Identifier` and comments with `sql.Literal`. Resource and dataset names reach SQL only as a literal comment.
- The orphan sweep refuses to run against a database that looks like the main one, never drops Django tables, and drops only names a person reviewed that are still unused.
- Logs carry ids, outcomes, counts and error codes. Never file contents, cell values or database error messages.

## SDK impact
SDK: no. This is storage-internal, and no public API changes shape.

## Tests

Tests marked `data_db` run against a real Postgres. Locally:

```
docker run -d --name dataspace-test-data-db -e POSTGRES_PASSWORD=postgres -p 55432:5432 postgres:16
export TEST_DATA_DB_URL=postgres://postgres:postgres@localhost:55432/postgres
pytest tests/data_index
```

How the setup works:
- **Database:** `tests/test_settings.py` adds the `data_db` alias only when `TEST_DATA_DB_URL` is set. pytest-django creates and drops `test_dataspace_data_db`, and `tests.data_index.routers.DataDbTestRouter` keeps Django models out of it.
- **Skipping:** without the URL these tests are skipped, unless `REQUIRE_DATA_DB_TESTS=1` (set in CI, which runs a `postgres:16` service). Then the run fails, because a run that skipped them proves nothing.
- **Clean-up:** an autouse fixture drops every `public` table after each such test, since pytest-django only empties tables of models routed there, and there are none.
- **Where it applies:** the skip/fail hook and that fixture live in `tests/data_index/conftest.py`, and `uses_data_db` in `tests/data_index/support.py`. Tests elsewhere that need them must move both into a shared conftest.
- **Main database:** stays in-memory SQLite, so row locks are no-ops there.
- **Locally:** if `drf_yasg` fails with "No module named pkg_resources", install `setuptools<81` (CI installs it).

### Layer 1 — DB helper tests
- **Naming:** a new row is named `rdt_<own id>`, and an existing row keeps its stored name on save. Two resources with names identical for 60+ characters get their own tables with their own rows.
- **Uploads:** a first upload creates the row, the table, the column rows and the comment. A re-upload switches to a new table, drops the old one and keeps custom descriptions.
- **Switch timing:** at the moment of the switch the new table is full and the old one still exists, and the lock is taken inside the switch transaction. The old table is dropped only after commit, with no transaction open and the new row saved.
- **Failures keep the old data:** a value out of range mid-copy keeps the old row and table, leaves no new table, and logs error code 22003 without the value. A 300-character header fails the switch, keeps the old row, table and column rows, and drops the new table.
- **Stopped runs:** a run stopped (KeyboardInterrupt) while the old table's after-commit drop waits keeps the new table the resource already points at. The clean-up keeps a table whose row is saved, drops one whose row isn't, and leaves it when the check fails.
- **Readers and races:** a reader still holding the old name gets "does not exist", never new rows. A slower build of an older file backs off when a newer file was saved, and the newer one stays.
- **Transaction and default:** indexing inside an outer transaction is refused and builds nothing. A re-upload keeps the row's `created` and the dataset's default table in the data API.
- **Deletes:** deleting a resource drops its table; deleting a dataset drops all its tables; a rolled-back delete keeps the table. Two legacy rows sharing a table: the table is kept until the last one is deleted. A drop of a table that's already gone doesn't fail. A drop blocked past the lock timeout is logged and the delete still succeeds.
- **Readers (regression):** on an `rdt_` table with a `%` header, the row count, preview, column list (including the `information_schema` fallback), filtered and ordered fetch, and a chart query all work.
- **Helpers:** indexable-file checks; load records the file identity, returns None for a header-only file, and cleans headers; the column rebuild lets DB errors escape and refuses over-long headers.
- **Migration — moving tables:**
  - a short table is renamed only on `--apply`;
  - a shared long table is rebuilt from each resource's own file, and the shared table is dropped after both rows move;
  - a single long table is rebuilt, not renamed;
  - with its file gone, a single long table is renamed and marked unverified, and later runs still list it;
  - with its file gone, a shared row stays while the other row moves;
  - a run after a crash just updates the row;
  - a rename blocked by a reader is skipped, then finished on a rerun.
- **Migration — orphans:** listed with size; drop needs `--from-report`; only reviewed names that are still orphans are dropped; young `rdt_` tables are never listed.
- **Migration — reruns and reports:**
  - a second `--apply` has nothing to do;
  - access models are listed;
  - the dry run shows the planned outcome per long table, the shared flag and `shared_groups`;
  - an unusable file (PDF) is marked unverified, or left while shared, and the runs settle on "nothing to do";
  - rebuilds read with no time limit;
  - a missing table is re-indexed or left for a person;
  - `--resource-id` limits the run;
  - a rename backs off when an upload replaced the row after planning.
- **Migration — refusals:** a bad reviewed report stops the run before any change; the report may not overwrite the reviewed file; the run refuses when the data database is the main one or holds `django_migrations`.

### Layer 2 — Non-DB helper tests
- **Names:** `rdt_` plus lowercase hex, 36 characters. The physical name is cut at 63 bytes and never mid-character.
- **Comment:** a resource name with quotes and semicolons is stored as text, not run as SQL.
- **Orphan rules:** Django tables, a row's tables, and fresh builds are excluded.
- **Registration:** the receiver is connected after app load (fresh interpreter).

### Layer 3 — Flow tests
- **Upload flow order:** load → name → build → lock → file check → retire → save → rebuild columns → confirm.
- **Clean-up:** the unswitched-build clean-up runs when the build, lock, retire or column rebuild fails, on a newer file, when the row is missing after commit, and on `KeyboardInterrupt`. It never runs after a confirmed switch.
- **Nothing to index:** nothing is built when inside a transaction, when there is no indexable file, or when nothing loaded.
- **Receiver:** schedules one guarded drop per deleted row, via `on_commit(robust=True)`.
- **Command:** the safety check runs first; a dry run changes nothing and writes the report; `--apply` runs row updates → renames → rebuilds (in plan order) → re-indexes; a failed safety check stops before any read; orphans are dropped only with `--apply` and a reviewed report.

### Layer 4 — Backend API e2e
As the dataset owner, through the GraphQL schema and the data API:
- `createFileResources` gives an `rdt_` table, and the data API returns its rows;
- `updateFileResource` with a new file serves the new rows and the old table is gone;
- `resetFileResourceSchema` switches to a fresh table;
- `deleteFileResource` drops the table, and the data API returns 404;
- `deleteDataset` drops every table.

Cross-org denial is unchanged and covered by `tests/schema/test_resource_permissions.py`.

### Layer 5 — API user journey
`tests/journeys/data_index/reupload-and-delete.py`, on request against a running backend (`KEYCLOAK_TEST_TOKEN`, `TEST_DATASET_ID`, `TEST_BASE_URL`):
1. Upload a CSV and read its rows.
2. Replace it while a thread polls the data API. Every read is the complete old file or the complete new one.
3. Fire two replacements at once. The data API serves the same file the download serves.
4. Delete the resource. The data API returns 404.

At least an hour later, the operator's dry run should list no orphan from the racing uploads.

### Layer 6 — Browser e2e
n/a — no UI change.

### Visual checklist (manual, on request)
n/a — no UI change.

### LLM-judge points
n/a — all assertions are deterministic.

---

## Failure model

| What could go wrong | Guarantee |
|---|---|
| Two resources map to one physical table | `rdt_<row id>` names are unique by construction. |
| A reader sees an empty or half-filled table | The new table is built fully before the switch, and the old one is dropped only after commit. |
| A failed re-upload wipes the data | The old row and table are untouched until the switch commits. |
| A failed build or switch leaves a stray table | `finally` drops it unless the switch is confirmed. |
| A rolled-back delete loses data | Drops run only `on_commit`. |
| The receiver drops a table another row still uses | Shared-name guard for old long names. |
| The receiver isn't loaded | Imported in `api/signals/__init__.py`, and a fresh-interpreter test checks it. |
| Two re-uploads race | Resource row lock plus the newest-file check. |
| A drop fails (lock, missing table) | Logged, never raised; the table becomes an orphan the command reports. |
| A rename gets stuck behind long reads | 2 s lock timeout; skipped, reported, and finished by a rerun. |
| The command crashes between rename and row update | The rerun updates the row; the "unverified" mark survives in the comment. |
| A shared table is rebuilt from the wrong file | Each row is rebuilt from its own file, and the table is dropped only after the last row moves. |
| A stored file is missing or unusable | Reported per row. An unshared table is marked unverified and listed in every report; a shared one is left for a person. |
| A collided table whose sharer was deleted gets renamed | Long old names are always rebuilt while the file is usable. |
| The orphan sweep deletes application tables or an in-flight upload's table | Same-database and Django-table refusals, the one-hour age guard, and only reviewed names dropped. |
| A swallowed error rolls the switch back silently | Column-row errors escape, the switch is confirmed by the row existing, and indexing refuses to run inside an outer transaction. |
| Test data tables leak between tests | An autouse fixture drops every `public` table after each `data_db` test. |

## Limitations & future work
- **A failed re-upload still reports success to the uploader.** This is existing behaviour: the mutations ignore the indexing result. Now the old data stays served while the download serves the new file, until a successful re-upload. Surfacing the failure would change the upload API's contract and is left for a decision.
- **Two long headers that differ only after 63 bytes** become one column in Postgres, so the build fails. Devanagari headers hit this at about 21 characters. This existed before and is not fixed here.
- **Access-model column selections are reset** whenever column rows are rebuilt (every re-upload, and migration rebuilds). Carrying them over by column name would be a small follow-up.
- **Readers still use f-string table names.** That is safe for `rdt_` names; they were left as they are deliberately.
- The plan's failure table said 5 s for the rename lock timeout. The design and the code use 2 s for renames and 5 s for drops.
