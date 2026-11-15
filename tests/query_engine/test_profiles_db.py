"""Layer 1: saving profiles only when they are still current, and their facts hashes (P1–P3)."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest

from api.models import DatasetProfile, ResourceProfile
from api.models.ResourceProfile import ResourceProfileStatus
from api.services.query_engine.profiles import (
    PROFILER_VERSION,
    dataset_rollup,
    ready_stats,
    record_profile_failure,
    save_resource_profile_if_current,
    write_dataset_facts_hash,
    write_resource_facts_hash,
)

STATS = {"row_count": 3, "columns": [], "layout": "long", "analysable": False}
NOW = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)


@pytest.mark.django_db
class TestSaveIfCurrent:
    def test_stores_ready_stats_for_the_current_data_table(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        table_id = resource.resourcedatatable.id

        assert save_resource_profile_if_current(resource, table_id, STATS) is True

        profile = ResourceProfile.objects.get(resource=resource)
        assert profile.status == ResourceProfileStatus.READY
        assert (profile.data_table_id, profile.stats) == (table_id, STATS)
        assert profile.profiler_version == PROFILER_VERSION

    def test_refuses_stats_computed_from_a_data_table_that_has_since_been_replaced(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())

        assert save_resource_profile_if_current(resource, uuid.uuid4(), STATS) is False
        assert not ResourceProfile.objects.filter(resource=resource).exists()

    def test_keeps_the_facts_hash_and_summary_when_restoring_stats(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        table_id = resource.resourcedatatable.id
        save_resource_profile_if_current(resource, table_id, STATS)
        ResourceProfile.objects.filter(resource=resource).update(
            facts_hash="h1", summary_text="Written earlier."
        )

        save_resource_profile_if_current(resource, table_id, {**STATS, "row_count": 4})

        profile = ResourceProfile.objects.get(resource=resource)
        assert (profile.facts_hash, profile.summary_text) == ("h1", "Written earlier.")
        assert profile.stats["row_count"] == 4


@pytest.mark.django_db
class TestFactsHashWrites:
    def test_a_new_hash_marks_the_summary_needed_and_resets_rejections(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)
        ResourceProfile.objects.filter(resource=resource).update(summary_rejections=2)
        profile = ResourceProfile.objects.get(resource=resource)

        assert write_resource_facts_hash(profile, "h1") is True

        profile.refresh_from_db()
        assert (profile.facts_hash, profile.summary_needed, profile.summary_rejections) == (
            "h1",
            True,
            0,
        )

    def test_the_same_hash_leaves_the_summary_state_alone(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)
        ResourceProfile.objects.filter(resource=resource).update(
            facts_hash="h1", summary_needed=False, summary_rejections=1
        )
        profile = ResourceProfile.objects.get(resource=resource)

        assert write_resource_facts_hash(profile, "h1") is False

        profile.refresh_from_db()
        assert (profile.summary_needed, profile.summary_rejections) == (False, 1)

    def test_a_write_from_a_stale_read_changes_nothing(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)
        stale = ResourceProfile.objects.get(resource=resource)
        ResourceProfile.objects.filter(resource=resource).update(facts_hash="moved")

        assert write_resource_facts_hash(stale, "h2") is False
        assert ResourceProfile.objects.get(resource=resource).facts_hash == "moved"

    def test_a_dataset_hash_creates_its_profile_row_the_first_time(
        self, make_dataset: Callable
    ) -> None:
        dataset = make_dataset()

        assert write_dataset_facts_hash(dataset, "d1") is True
        assert write_dataset_facts_hash(dataset, "d1") is False

        profile = DatasetProfile.objects.get(dataset=dataset)
        assert (profile.facts_hash, profile.summary_needed) == ("d1", True)


@pytest.mark.django_db
class TestFailures:
    def test_each_failure_on_the_same_table_doubles_the_wait(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        table_id = resource.resourcedatatable.id

        first = record_profile_failure(resource, table_id, "query_too_slow", now=NOW)
        second = record_profile_failure(resource, table_id, "query_too_slow", now=NOW)

        assert first.failed_attempts == 1 and first.retry_after == NOW + timedelta(minutes=2)
        assert second.failed_attempts == 2 and second.retry_after == NOW + timedelta(minutes=4)
        assert second.status == ResourceProfileStatus.FAILED
        assert second.error == "query_too_slow"

    def test_the_wait_is_capped_at_a_day(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        table_id = resource.resourcedatatable.id
        ResourceProfile.objects.create(
            resource=resource,
            data_table_id=table_id,
            profiler_version=PROFILER_VERSION,
            status=ResourceProfileStatus.FAILED,
            failed_attempts=20,
        )

        profile = record_profile_failure(resource, table_id, "query_failed", now=NOW)

        assert profile.retry_after == NOW + timedelta(hours=24)

    def test_a_new_data_table_resets_the_attempts_and_drops_old_stats(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)
        record_profile_failure(resource, resource.resourcedatatable.id, "query_failed", now=NOW)

        profile = record_profile_failure(resource, uuid.uuid4(), "query_failed", now=NOW)

        assert profile.failed_attempts == 1
        assert profile.stats is None

    def test_a_failure_on_the_same_table_keeps_its_last_good_stats(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)

        profile = record_profile_failure(
            resource, resource.resourcedatatable.id, "query_failed", now=NOW
        )

        assert profile.stats == STATS


@pytest.mark.django_db
class TestReadyStatsAndRollup:
    def test_stats_count_only_when_ready_for_the_current_table(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)
        resource.refresh_from_db()
        assert ready_stats(resource) == STATS

        ResourceProfile.objects.filter(resource=resource).update(data_table_id=uuid.uuid4())
        resource.refresh_from_db()
        assert ready_stats(resource) is None

    def test_the_rollup_lists_tables_and_other_resources(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        dataset = make_dataset("Health")
        table = make_resource(dataset, name="Indicators")
        make_resource(dataset, name="Methodology note", with_table=False)
        save_resource_profile_if_current(
            table, table.resourcedatatable.id, {**STATS, "analysable": True}
        )

        rollup = dataset_rollup(dataset)

        assert [t["name"] for t in rollup["tables"]] == ["Indicators"]
        assert rollup["tables"][0]["analysable"] is True
        assert rollup["other_resources"] == [{"name": "Methodology note", "format": "file"}]

