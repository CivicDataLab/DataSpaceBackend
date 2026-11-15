"""One ``qe_sync`` pass at a time, across every process and container.

A Postgres advisory lock on the data database's connection (session level,
so it lives across the pass's many short read-only transactions and is freed
by Postgres if the process dies and its connection closes). Loop passes try
once and skip when another process holds it; one-shot runs may wait.

Docs: api/views/query_engine/architecture.md
"""

import time
from contextlib import contextmanager
from typing import Iterator

from django.db import connections

from api.utils.data_tables import DATA_DB

# Any fixed 64-bit number; only qe_sync uses it.
SYNC_LOCK_KEY = 0x5145_5359_4E43  # "QESYNC"
WAIT_STEP_SECONDS = 1.0


def _try_lock() -> bool:
    with connections[DATA_DB].cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [SYNC_LOCK_KEY])
        return bool(cursor.fetchone()[0])


def _unlock() -> None:
    with connections[DATA_DB].cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [SYNC_LOCK_KEY])


@contextmanager
def sync_lock(wait_seconds: float = 0) -> Iterator[bool]:
    """Hold the pass lock for the block; yields whether it was taken.

    Waits up to ``wait_seconds`` for another holder to finish (0: try once).
    Always released on the way out, also when the block raises.
    """
    deadline = time.monotonic() + wait_seconds
    held = _try_lock()
    while not held and time.monotonic() < deadline:
        time.sleep(WAIT_STEP_SECONDS)
        held = _try_lock()
    try:
        yield held
    finally:
        if held:
            _unlock()
