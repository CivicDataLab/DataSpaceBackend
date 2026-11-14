"""How tables in the data database are named.

Every tabular upload gets its own table, named "rdt_" plus the 32-character
hex of its ResourceDataTable row id (36 characters in all). The name never
depends on a resource or dataset title, so renames don't touch it and two
uploads can never share one.

Postgres keeps only the first 63 bytes of any name. Names from before this
rule were built from titles (up to 110 characters), so two of them can map to
the same physical table; ``physical_table_name`` gives the name Postgres
actually stored, for the checks that care.

No imports from models: the ResourceDataTable model uses this module.
Docs: ./data_indexing_architecture.md
"""

import uuid

DATA_TABLE_PREFIX = "rdt_"
MAX_IDENTIFIER_BYTES = 63
# A cut name is at least this long: a cut never drops more than a 4-byte character's first 3 bytes.
SHORTEST_CUT_NAME_BYTES = MAX_IDENTIFIER_BYTES - 3


def data_table_name(row_id: uuid.UUID) -> str:
    """The table name for a ResourceDataTable row: "rdt_" + its id in lowercase hex."""
    return f"{DATA_TABLE_PREFIX}{row_id.hex}"


def physical_table_name(name: str) -> str:
    """The name Postgres stores for ``name``: its first 63 bytes, never half a character."""
    encoded = name.encode("utf-8")
    if len(encoded) <= MAX_IDENTIFIER_BYTES:
        return name
    return encoded[:MAX_IDENTIFIER_BYTES].decode("utf-8", errors="ignore")


def may_share_physical_table(name: str) -> bool:
    """Whether another, longer name could be cut to the same physical table as this one.

    Only names at least as long as the shortest possible cut can; "rdt_" names
    (36 bytes) never can.
    """
    return len(name.encode("utf-8")) >= SHORTEST_CUT_NAME_BYTES
