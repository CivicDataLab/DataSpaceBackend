"""Layer 1: which tables a pass profiles, and facts refreshed from current metadata (SYNC2, SYNC6–8).

Real ORM; profiling itself (the data-database part) is replaced by a plain
function where a test only cares which tables get profiled.
"""

import uuid
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List

import pytest

from api.models import Organization, Resource, ResourceProfile, ResourceSchema
from api.models.ResourceProfile import ResourceProfileStatus
from api.services.query_engine.corpus import load_corpus
from api.services.query_engine.errors import QueryTooSlow
from api.services.query_engine.geography_match import GeographyIndex
from api.services.query_engine.profiles import (
    PROFILER_VERSION,
    save_resource_profile_if_current,
)
from api.services.query_engine.sync_pass import run_sync_pass
from api.services.query_engine.sync_steps import (
    FAILED,
    PROFILED,
    find_stale_profiles,
    profile_one,
    refresh_facts,
)
from tests.data_index.support import uses_data_db


@contextmanager
def _free_lock(wait_seconds: float = 0) -> Iterator[bool]:
    yield True


NOW = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)
STATS = {
    "row_count": 2,
    "layout": "long",
    "analysable": True,
    "columns": [
        {"name": "IMR", "profiled": True, "kind": "numeric", "role": "measure"}
    ],
}


def chunk() -> List[Any]:
    return [dataset for page in load_corpus() for dataset in page]


def stale_names() -> List[str]:
    return [resource.name for resource in find_stale_profiles(chunk(), NOW)]


@pytest.mark.django_db
class TestFindStaleProfiles:
    def test_a_table_with_no_profile_is_stale_and_a_current_one_is_not(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        dataset = make_dataset()
        fresh = make_resource(dataset, name="Fresh")
        make_resource(dataset, name="New")
        make_resource(dataset, name="Report", with_table=False)
        save_resource_profile_if_current(fresh, fresh.resourcedatatable.id, STATS)

        assert stale_names() == ["New"]

    def test_a_re_upload_or_a_newer_profiler_makes_it_stale(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        dataset = make_dataset()
        uploaded = make_resource(dataset, name="Re-uploaded")
        old_version = make_resource(dataset, name="Old profiler")
        for resource in (uploaded, old_version):
            save_resource_profile_if_current(
                resource, resource.resourcedatatable.id, STATS
            )
        ResourceProfile.objects.filter(resource=uploaded).update(
            data_table_id=uuid.uuid4()
        )
        ResourceProfile.objects.filter(resource=old_version).update(
            profiler_version=PROFILER_VERSION - 1
        )

        assert stale_names() == ["Old profiler", "Re-uploaded"]

    def test_a_failed_retry_of_an_old_version_waits_out_its_back_off(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset(), name="Old version")
        ResourceProfile.objects.create(
            resource=resource,
            data_table_id=resource.resourcedatatable.id,
            profiler_version=PROFILER_VERSION - 1,
            status=ResourceProfileStatus.READY,
            failed_attempts=1,
            retry_after=NOW + timedelta(minutes=5),
        )
        assert stale_names() == []

    def test_a_failed_table_waits_out_its_back_off(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        dataset = make_dataset()
        waiting = make_resource(dataset, name="Waiting")
        due = make_resource(dataset, name="Due")
        for resource, retry in ((waiting, NOW + timedelta(minutes=5)), (due, NOW)):
            ResourceProfile.objects.create(
                resource=resource,
                data_table_id=resource.resourcedatatable.id,
                profiler_version=PROFILER_VERSION,
                status=ResourceProfileStatus.FAILED,
                failed_attempts=1,
                retry_after=retry,
            )

        assert stale_names() == ["Due"]

    def test_one_resource_narrows_to_it(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        dataset = make_dataset()
        first = make_resource(dataset, name="First")
        make_resource(dataset, name="Second")
        save_resource_profile_if_current(first, first.resourcedatatable.id, STATS)

        only = find_stale_profiles(chunk(), NOW, only_resource_id=first.id)

        assert [r.name for r in only] == ["First"]

    def test_a_reprofile_request_is_stored_so_passes_finish_every_table(
        self,
        make_dataset: Callable,
        make_resource: Callable,
        monkeypatch: Any,
        settings: Any,
    ) -> None:
        dataset = make_dataset()
        resources = [make_resource(dataset, name=f"Table {i}") for i in range(5)]
        for resource in resources:
            save_resource_profile_if_current(
                resource, resource.resourcedatatable.id, STATS
            )
        monkeypatch.setattr(
            "api.services.query_engine.sync_pass.close_old_connections", lambda: None
        )
        monkeypatch.setattr("api.services.query_engine.sync_pass.sync_lock", _free_lock)
        monkeypatch.setattr(
            "api.services.query_engine.sync_pass.open_search_index",
            lambda: None,
            raising=False,
        )
        monkeypatch.setattr(
            "api.services.query_engine.sync_steps.build_resource_stats",
            lambda r, g, t=None: STATS,
        )
        settings.QE_PROFILES_PER_PASS = 2

        first = run_sync_pass(reprofile=True)
        later = [run_sync_pass().profiles.get("profiled", 0) for _ in range(3)]

        assert first.marked_for_reprofile == 5
        assert first.profiles == {"profiled": 2}
        assert later == [2, 1, 0]


@pytest.mark.django_db
class TestProfileOne:
    def test_saves_stats_for_the_current_table(
        self, make_dataset: Callable, make_resource: Callable, monkeypatch: Any
    ) -> None:
        resource = make_resource(make_dataset())
        monkeypatch.setattr(
            "api.services.query_engine.sync_steps.build_resource_stats",
            lambda r, g, t=None: STATS,
        )

        assert profile_one(resource, GeographyIndex()) == PROFILED
        assert resource.qe_profile.status == ResourceProfileStatus.READY
        # Its facts hash is written at once, not only at the end of the chunk.
        assert ResourceProfile.objects.get(resource=resource).facts_hash != ""

    def test_a_failure_is_stored_and_never_raised(
        self, make_dataset: Callable, make_resource: Callable, monkeypatch: Any
    ) -> None:
        resource = make_resource(make_dataset())

        def too_slow(
            resource: Resource, geography: GeographyIndex, budget: Any = None
        ) -> Dict:
            raise QueryTooSlow()

        monkeypatch.setattr(
            "api.services.query_engine.sync_steps.build_resource_stats", too_slow
        )

        assert profile_one(resource, GeographyIndex()) == "failed:query_too_slow"
        stored = ResourceProfile.objects.get(resource=resource)
        assert (stored.status, stored.error, stored.failed_attempts) == (
            "FAILED",
            "query_too_slow",
            1,
        )

    def test_an_unexpected_error_is_stored_as_a_code(
        self, make_dataset: Callable, make_resource: Callable, monkeypatch: Any
    ) -> None:
        resource = make_resource(make_dataset())

        def broken(
            resource: Resource, geography: GeographyIndex, budget: Any = None
        ) -> Dict:
            raise KeyError("cell value")

        monkeypatch.setattr(
            "api.services.query_engine.sync_steps.build_resource_stats", broken
        )

        assert profile_one(resource, GeographyIndex()) == "failed:profile_failed"
        assert ResourceProfile.objects.get(resource=resource).error == "profile_failed"


@pytest.mark.django_db
class TestRefreshFacts:
    def _profiled(self, make_dataset: Callable, make_resource: Callable) -> Resource:
        resource = make_resource(make_dataset())
        ResourceSchema.objects.create(
            resource=resource, field_name="IMR", format="NUMBER"
        )
        save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)
        return resource

    def test_writes_hashes_once_and_nothing_on_a_second_pass(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        self._profiled(make_dataset, make_resource)

        assert refresh_facts(chunk()) == {"resources": 1, "datasets": 1}
        assert refresh_facts(chunk()) == {"resources": 0, "datasets": 0}

    def test_a_description_edit_rewrites_facts_without_reprofiling(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = self._profiled(make_dataset, make_resource)
        refresh_facts(chunk())
        before = ResourceProfile.objects.get(resource=resource)
        ResourceSchema.objects.filter(resource=resource).update(
            description="Infant mortality"
        )

        assert stale_names() == []
        assert refresh_facts(chunk())["resources"] == 1
        after = ResourceProfile.objects.get(resource=resource)
        assert after.facts_hash != before.facts_hash
        assert after.stats == before.stats
        assert after.summary_needed is True

    def test_an_organisation_renamed_by_a_bulk_update_changes_the_facts(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = self._profiled(make_dataset, make_resource)
        refresh_facts(chunk())
        Organization.objects.filter(pk=resource.dataset.organization_id).update(
            name="Renamed Org"
        )

        assert refresh_facts(chunk()) == {"resources": 1, "datasets": 1}

    def test_a_pass_that_stopped_after_profiling_is_finished_by_the_next(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        # The profile was saved, then the process died before facts were written.
        resource = self._profiled(make_dataset, make_resource)
        assert ResourceProfile.objects.get(resource=resource).facts_hash == ""

        assert stale_names() == []
        assert refresh_facts(chunk())["resources"] == 1
        assert ResourceProfile.objects.get(resource=resource).facts_hash != ""


@uses_data_db
def test_a_real_pass_profiles_a_new_upload_and_a_second_pass_does_nothing(
    make_table_resource: Callable, geography: GeographyIndex
) -> None:
    resource = make_table_resource("district_health.csv")

    first = run_sync_pass()
    second = run_sync_pass()

    profile = ResourceProfile.objects.get(resource=resource)
    assert profile.status == ResourceProfileStatus.READY
    assert profile.stats["row_count"] == 8
    assert profile.facts_hash and profile.summary_needed
    assert first.profiles == {"profiled": 1}
    # The table's facts hash is written as soon as it is profiled; the dataset's at the chunk's end.
    assert (first.resource_facts_changed, first.dataset_facts_changed) == (0, 1)
    assert second.profiles == {}
    assert (second.resource_facts_changed, second.dataset_facts_changed) == (0, 0)


@pytest.mark.django_db
def test_an_incomplete_profile_is_tried_again_later(
    make_dataset: Callable, make_resource: Callable
) -> None:
    resource = make_resource(make_dataset())
    save_resource_profile_if_current(
        resource, resource.resourcedatatable.id, {**STATS, "stats_complete": False}
    )
    profile = ResourceProfile.objects.get(resource=resource)
    assert profile.retry_after is not None

    chunk = [d for page in load_corpus() for d in page]
    assert find_stale_profiles(chunk, profile.retry_after - timedelta(minutes=1)) == []
    assert [r.id for r in find_stale_profiles(chunk, profile.retry_after)] == [
        resource.id
    ]
