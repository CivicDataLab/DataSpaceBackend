"""Regression test: the migration graph must have a single leaf per app.

Root cause: ``0056_file_field_storages`` (s3_migration) and ``0056_update_license_choices``
(dev) both depended on ``0055_event``, and dev then added ``0057`` on top of its own branch.
Merging dev left two leaf nodes, so ``manage.py migrate`` aborted with "Conflicting migrations
detected" and the container never started. The suite did not notice because ``--nomigrations``
hides the real migration modules.

Fix: renumber the branch's migration after the latest one on dev and fix its ``dependencies``.
"""

from django.db.migrations.loader import MigrationLoader
from django.test import override_settings


# pytest's --nomigrations disables MIGRATION_MODULES, which would leave an empty graph here and
# make these tests pass whatever is on disk, so restore the real modules.
@override_settings(MIGRATION_MODULES={})
def test_migration_graph_has_no_conflicts() -> None:
    assert MigrationLoader(None).detect_conflicts() == {}


@override_settings(MIGRATION_MODULES={})
def test_migration_graph_is_actually_loaded() -> None:
    # Guards the test above against passing on an empty graph.
    assert MigrationLoader(None).graph.leaf_nodes("api")
