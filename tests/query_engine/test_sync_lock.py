"""Layer 1 (real Postgres data database): one sync pass at a time (LK1)."""

import psycopg2
import pytest
from django.db import connections

from api.services.query_engine.sync_lock import SYNC_LOCK_KEY, sync_lock
from tests.data_index.support import DATA_DB, uses_data_db


def other_connection_can_lock() -> bool:
    """Whether a second, independent connection could take the lock right now (then frees it)."""
    other = psycopg2.connect(**connections[DATA_DB].get_connection_params())
    other.autocommit = True
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [SYNC_LOCK_KEY])
            taken = bool(cursor.fetchone()[0])
            if taken:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [SYNC_LOCK_KEY])
            return taken
    finally:
        other.close()


@uses_data_db
def test_a_second_connection_cannot_take_the_lock_while_it_is_held() -> None:
    with sync_lock() as held:
        assert held is True
        assert other_connection_can_lock() is False
    assert other_connection_can_lock() is True


@uses_data_db
def test_the_lock_is_released_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError):
        with sync_lock():
            raise RuntimeError("pass failed")
    assert other_connection_can_lock() is True


@uses_data_db
def test_the_lock_is_freed_when_the_holders_connection_closes() -> None:
    holder = psycopg2.connect(**connections[DATA_DB].get_connection_params())
    holder.autocommit = True
    with holder.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [SYNC_LOCK_KEY])
    with sync_lock() as held:
        assert held is False
    holder.close()
    with sync_lock() as held:
        assert held is True


@uses_data_db
def test_a_held_lock_is_skipped_after_the_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.services.query_engine.sync_lock.WAIT_STEP_SECONDS", 0.05)
    holder = psycopg2.connect(**connections[DATA_DB].get_connection_params())
    holder.autocommit = True
    try:
        with holder.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [SYNC_LOCK_KEY])
        with sync_lock(wait_seconds=0.2) as held:
            assert held is False
    finally:
        holder.close()
