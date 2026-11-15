"""Layer 3: the order and limits of one sync pass, with every helper mocked (SYNC1, SYNC7)."""

import itertools
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterator, List
from unittest import mock

import pytest

from api.services.query_engine import sync_pass

FLOW = "api.services.query_engine.sync_pass"


@pytest.fixture
def helpers(settings: Any) -> Iterator[mock.MagicMock]:
    """Every helper the flow calls, recorded in one call log."""
    settings.QE_PROFILES_PER_PASS = 50
    settings.QE_SYNC_MAX_SECONDS = 100
    calls = mock.MagicMock()

    @contextmanager
    def lock(wait_seconds: float = 0) -> Iterator[bool]:
        calls.lock(wait_seconds)
        try:
            yield calls.lock_held
        finally:
            calls.unlock()

    calls.lock_held = True
    chunk = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    calls.load_corpus.return_value = iter([chunk])
    calls.find_stale_profiles.return_value = ["table-a", "table-b", "table-c"]
    calls.profile_one.return_value = "profiled"
    calls.refresh_facts.return_value = {"resources": 2, "datasets": 1}
    with mock.patch.multiple(
        FLOW,
        close_old_connections=calls.close_old_connections,
        sync_lock=lock,
        load_geography_index=calls.load_geography_index,
        load_corpus=calls.load_corpus,
        find_stale_profiles=calls.find_stale_profiles,
        profile_one=calls.profile_one,
        refresh_facts=calls.refresh_facts,
    ):
        yield calls


def call_names(calls: mock.MagicMock) -> List[str]:
    return [name for name, _, _ in calls.mock_calls if not name.startswith("lock_held")]


def test_a_pass_runs_its_steps_in_order(helpers: mock.MagicMock) -> None:
    report = sync_pass.run_sync_pass()

    names = call_names(helpers)
    assert names[:4] == [
        "close_old_connections",
        "lock",
        "load_geography_index",
        "load_corpus",
    ]
    assert names[4:] == [
        "find_stale_profiles",
        "profile_one",
        "profile_one",
        "profile_one",
        "refresh_facts",
        "unlock",
    ]
    assert report.profiles == {"profiled": 3}
    assert (
        report.datasets,
        report.resource_facts_changed,
        report.dataset_facts_changed,
    ) == (
        2,
        2,
        1,
    )


def test_waiting_for_the_lock_does_not_eat_the_time_budget(
    helpers: mock.MagicMock, settings: Any
) -> None:
    # 150 s pass while waiting for the lock; the 100 s budget must start after that.
    clock = itertools.chain([0.0], itertools.count(150.0))
    with mock.patch("time.monotonic", side_effect=lambda: next(clock)):
        sync_pass.run_sync_pass(lock_wait_seconds=200)

    helpers.lock.assert_called_once_with(200)
    assert helpers.profile_one.call_count == 3


def test_reprofile_marks_every_table_first(helpers: mock.MagicMock) -> None:
    with mock.patch(f"{FLOW}.mark_for_reprofile", return_value=7) as mark:
        report = sync_pass.run_sync_pass(reprofile=True)
    mark.assert_called_once()
    assert report.marked_for_reprofile == 7


def test_nothing_runs_when_another_pass_holds_the_lock(helpers: mock.MagicMock) -> None:
    helpers.lock_held = False

    report = sync_pass.run_sync_pass()

    assert report.skipped is True
    helpers.load_corpus.assert_not_called()
    helpers.profile_one.assert_not_called()


def test_the_profile_cap_holds(helpers: mock.MagicMock, settings: Any) -> None:
    settings.QE_PROFILES_PER_PASS = 2

    report = sync_pass.run_sync_pass()

    assert helpers.profile_one.call_count == 2
    assert report.profiles == {"profiled": 2}
    # Facts are still refreshed for the whole chunk.
    helpers.refresh_facts.assert_called_once()


def test_the_time_budget_stops_profiling(
    helpers: mock.MagicMock, settings: Any
) -> None:
    settings.QE_SYNC_MAX_SECONDS = 0

    sync_pass.run_sync_pass()

    helpers.profile_one.assert_not_called()
    helpers.refresh_facts.assert_called_once()


def test_one_failed_table_does_not_stop_the_others(helpers: mock.MagicMock) -> None:
    helpers.profile_one.side_effect = ["failed", "profiled", "profiled"]

    report = sync_pass.run_sync_pass()

    assert report.profiles == {"failed": 1, "profiled": 2}


def test_the_lock_is_released_when_a_step_raises(helpers: mock.MagicMock) -> None:
    helpers.refresh_facts.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        sync_pass.run_sync_pass()

    assert call_names(helpers)[-1] == "unlock"
