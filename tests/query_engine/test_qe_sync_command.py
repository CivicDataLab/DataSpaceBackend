"""Layer 3: the ``qe_sync`` command's modes (CMD1, profiling parts)."""

from typing import Any, List
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from api.services.query_engine.sync_steps import SyncReport

PASS = "api.management.commands.qe_sync.run_sync_pass"


class StopLoop(Exception):
    pass


def test_once_runs_one_pass_and_waits_for_the_lock(settings: Any) -> None:
    settings.QE_SYNC_MAX_SECONDS = 100
    with mock.patch(PASS, return_value=SyncReport(datasets=3)) as run:
        call_command("qe_sync", "--once")
    run.assert_called_once_with(
        reprofile=False, only_resource_id=None, lock_wait_seconds=200
    )


def test_reprofile_and_one_resource_are_passed_on() -> None:
    with mock.patch(PASS, return_value=SyncReport(profiles={"profiled": 1})) as run:
        call_command("qe_sync", "--reprofile")
        call_command("qe_sync", "--resource-id", "8c1d2a3e-0000-4000-8000-000000000001")
    assert run.call_args_list[0].kwargs["reprofile"] is True
    assert str(run.call_args_list[1].kwargs["only_resource_id"]) == (
        "8c1d2a3e-0000-4000-8000-000000000001"
    )


def test_a_one_shot_run_that_never_gets_the_lock_fails_loudly() -> None:
    with mock.patch(PASS, return_value=SyncReport(skipped=True)):
        with pytest.raises(CommandError, match="held the lock"):
            call_command("qe_sync", "--once")


def test_naming_a_table_that_was_not_profiled_fails() -> None:
    with mock.patch(
        PASS, return_value=SyncReport(profiles={"failed:query_too_slow": 1})
    ):
        with pytest.raises(CommandError, match="not profiled"):
            call_command(
                "qe_sync", "--resource-id", "8c1d2a3e-0000-4000-8000-000000000001"
            )
    with mock.patch(PASS, return_value=SyncReport()):
        with pytest.raises(CommandError, match="not profiled"):
            call_command(
                "qe_sync", "--resource-id", "8c1d2a3e-0000-4000-8000-000000000001"
            )
    with mock.patch(PASS, return_value=SyncReport(profiles={"profiled": 1})):
        call_command("qe_sync", "--resource-id", "8c1d2a3e-0000-4000-8000-000000000001")


def test_a_mode_is_required() -> None:
    with pytest.raises(CommandError):
        call_command("qe_sync")


def test_the_loop_logs_a_failed_pass_and_runs_the_next() -> None:
    outcomes: List[Any] = [RuntimeError("pass blew up"), SyncReport(datasets=1)]
    sleeps: List[float] = []

    def next_pass(**kwargs: Any) -> SyncReport:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if not outcomes:
            raise StopLoop()

    with mock.patch(PASS, side_effect=next_pass) as run, mock.patch(
        "api.management.commands.qe_sync.time.sleep", side_effect=sleep
    ), mock.patch("api.management.commands.qe_sync.logger") as log:
        with pytest.raises(StopLoop):
            call_command("qe_sync", "--loop")

    assert run.call_count == 2
    assert len(sleeps) == 2
    log.error.assert_called_once()
    assert "pass blew up" not in str(log.error.call_args)
