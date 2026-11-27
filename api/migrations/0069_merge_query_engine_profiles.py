"""Joins the query engine's profile tables (0066_query_engine_profiles) with dev.

The query engine branch added its 0066 while dev added 0066–0068, so both have
a migration after 0065. This merge keeps one migration leaf. It changes nothing
in the database.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0066_query_engine_profiles"),
        ("api", "0068_link_publication_contributors"),
    ]

    operations = []
