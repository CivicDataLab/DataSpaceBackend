"""Joins the main hotfix migration 0054_rebuild_long_text_search_indexes with dev.

The hotfix went to main on its own (main was at 0053), so both branches have a
migration after their own parent. This merge keeps one migration leaf. Both
rebuild migrations do the same thing and do nothing once indexes are clean.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0064_rebuild_long_text_search_indexes"),
        ("api", "0054_rebuild_long_text_search_indexes"),
    ]

    operations = []
