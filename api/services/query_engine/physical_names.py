"""The name Postgres actually stores for a column header.

A column's identity is its full header (what the uploader wrote, kept in
ResourceSchema.field_name). Postgres keeps only the first 63 bytes of any
name, cut on a character boundary — about 21 Devanagari characters — so the
catalogue (pg_attribute) holds the cut name. Queries can still name the full
header: Postgres cuts it the same way. This is the same rule the data index
uses for table names, so it reuses that helper.

Docs: api/views/query_engine/architecture.md
"""

from api.utils.data_table_names import physical_table_name


def physical_column_name(header: str) -> str:
    """The header's first 63 UTF-8 bytes, never half a character (unchanged when shorter)."""
    return physical_table_name(header)
