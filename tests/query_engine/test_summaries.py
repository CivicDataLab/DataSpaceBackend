"""Layer 1 + 3 + 4: pending summaries, safe writes, and the write endpoint (SUM1–SUM6, SV1, SUM, LEAK4, LOG)."""

import logging
from typing import Any, Callable, Dict, List
from unittest import mock

import pytest

from api.models import Dataset, DatasetProfile, Resource, ResourceProfile, ResourceSchema
from api.services.query_engine.corpus import load_corpus
from api.services.query_engine.profiles import save_resource_profile_if_current
from api.services.query_engine.summaries import (
    get_summary_target,
    pending_summaries,
    record_rejection,
    save_summary_if_current,
)
from api.services.query_engine.sync_steps import refresh_facts
from api.utils.enums import DatasetAccessType, DatasetStatus

STATS: Dict[str, Any] = {
    "row_count": 3,
    "layout": "long",
    "analysable": True,
    "columns": [
        {"name": "District", "profiled": True, "kind": "text", "role": "dimension", "distinct": 3},
        {
            "name": "Cases",
            "profiled": True,
            "kind": "numeric",
            "role": "measure",
            "min": 4.0,
            "max": 19.0,
        },
    ],
}
GOOD = (
    "Counts of cases across 3 districts, ranging from 4 to 19, with one row per district "
    "and no breakdown by year or sex."
)
DATASET_GOOD = (
    "One table of case counts by district from Health Org: 3 rows and 2 columns, "
    "with no breakdown by year or sex and no other files."
)


def sync_facts() -> None:
    refresh_facts([d for page in load_corpus() for d in page])


@pytest.fixture
def profiled(make_dataset: Callable, make_resource: Callable) -> Callable[..., Resource]:
    """A table with READY stats and its facts hashes written, as after a sync pass."""

    def make(title: str = "Cases", ready: bool = True, **changes: Any) -> Resource:
        resource = make_resource(make_dataset(title, **changes), name=f"{title} table")
        ResourceSchema.objects.create(resource=resource, field_name="Cases", format="NUMBER")
        if ready:
            save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)
        sync_facts()
        return Resource.objects.get(pk=resource.pk)

    return make


def profile_of(resource: Resource) -> ResourceProfile:
    return ResourceProfile.objects.get(resource=resource)


def pending_ids() -> List[str]:
    return [item["id"] for item in pending_summaries(20)]


@pytest.mark.django_db
class TestPending:
    def test_lists_needed_ready_items_in_the_corpus(self, profiled: Callable) -> None:
        resource = profiled()
        item = next(i for i in pending_summaries(20) if i["level"] == "resource")
        assert item["id"] == str(resource.id)
        assert item["facts_hash"] == profile_of(resource).facts_hash
        assert item["facts"]["columns"][1]["max"] == 19.0
        assert str(resource.dataset_id) in pending_ids()

    def test_never_lists_private_or_unpublished_items(self, profiled: Callable) -> None:
        private = profiled("Private", access_type=DatasetAccessType.PUBLIC)
        draft = profiled("Draft")
        Dataset.objects.filter(pk=private.dataset_id).update(access_type=DatasetAccessType.PRIVATE)
        Dataset.objects.filter(pk=draft.dataset_id).update(status=DatasetStatus.DRAFT)
        assert pending_ids() == []

    def test_skips_items_rejected_twice_and_items_already_written(self, profiled: Callable) -> None:
        rejected = profiled("Rejected")
        written = profiled("Written")
        ResourceProfile.objects.filter(resource=rejected).update(summary_rejections=2)
        ResourceProfile.objects.filter(resource=written).update(summary_needed=False)
        ids = pending_ids()
        assert str(rejected.id) not in ids and str(written.id) not in ids

    def test_oldest_change_first_and_the_limit_holds(self, profiled: Callable) -> None:
        resources = [profiled(f"Table {i}") for i in range(3)]
        DatasetProfile.objects.update(summary_needed=False)
        items = pending_summaries(2)
        assert [i["id"] for i in items] == [str(r.id) for r in resources[:2]]
        assert len(pending_summaries(500)) == 3

    def test_a_dataset_waits_until_all_its_tables_are_ready(
        self, profiled: Callable, make_resource: Callable
    ) -> None:
        resource = profiled()
        unready = make_resource(resource.dataset, name="Second table")
        assert str(resource.dataset_id) not in pending_ids()
        save_resource_profile_if_current(unready, unready.resourcedatatable.id, STATS)
        sync_facts()
        assert str(resource.dataset_id) in pending_ids()

    def test_items_outside_the_rollout_are_not_offered(
        self, profiled: Callable, settings: Any, make_sector: Callable
    ) -> None:
        climate = make_sector("Climate Action")
        kept = profiled("Rainfall")
        kept.dataset.sectors.add(climate)
        other = profiled("Anaemia")
        settings.QE_PLATFORM_SECTORS = ["climate-action"]
        ids = pending_ids()
        assert str(kept.id) in ids and str(other.id) not in ids

    def test_a_failed_or_outdated_table_is_neither_offered_nor_accepted(
        self, profiled: Callable, api: Callable
    ) -> None:
        import uuid as uuidlib

        failed = profiled("Failed")
        outdated = profiled("Outdated")
        ResourceProfile.objects.filter(resource=failed).update(status="FAILED")
        ResourceProfile.objects.filter(resource=outdated).update(data_table_id=uuidlib.uuid4())
        ids = pending_ids()
        assert str(failed.id) not in ids and str(outdated.id) not in ids
        current = profile_of(outdated).facts_hash
        assert api().put(url("resource", outdated), body(current), format="json").status_code == 404

    def test_skipped_datasets_never_block_the_ones_behind_them(
        self, profiled: Callable, make_resource: Callable
    ) -> None:
        blocked = [profiled(f"Blocked {i}") for i in range(12)]
        for resource in blocked:
            make_resource(resource.dataset, name="Never profiled")
        ready = profiled("Ready")
        ResourceProfile.objects.update(summary_needed=False)
        # The blocked datasets are the oldest changes, so they come first in the queue.
        from datetime import datetime, timezone as tz

        DatasetProfile.objects.filter(dataset_id__in=[r.dataset_id for r in blocked]).update(
            modified=datetime(2026, 1, 1, tzinfo=tz.utc)
        )
        DatasetProfile.objects.filter(dataset_id=ready.dataset_id).update(
            modified=datetime(2026, 6, 1, tzinfo=tz.utc)
        )
        assert [i["id"] for i in pending_summaries(5)] == [str(ready.dataset_id)]

    def test_big_facts_are_cut_to_8000_characters(
        self, profiled: Callable, monkeypatch: Any
    ) -> None:
        resource = profiled()
        wide = {
            **STATS,
            "columns": [
                {**STATS["columns"][1], "name": f"Indicator {i:03d} " + "x" * 80}
                for i in range(200)
            ],
        }
        ResourceProfile.objects.filter(resource=resource).update(stats=wide)
        sync_facts()
        item = next(i for i in pending_summaries(20) if i["level"] == "resource")
        import json

        assert len(json.dumps(item["facts"], ensure_ascii=False)) <= 8000
        assert item["facts"]["columns_omitted"] > 0


@pytest.mark.django_db
class TestWrites:
    def test_a_write_with_the_current_hash_stores_it_and_clears_needed(
        self, profiled: Callable
    ) -> None:
        resource = profiled()
        target = get_summary_target("resource", resource.id)
        current = target.profile.facts_hash

        assert save_summary_if_current(target, current, GOOD, "model-x", "pv1") is True

        profile = profile_of(resource)
        assert (profile.summary_text, profile.summary_facts_hash, profile.summary_needed) == (
            GOOD,
            current,
            False,
        )
        assert (profile.summary_model, profile.summary_prompt_version) == ("model-x", "pv1")

    def test_a_write_with_an_old_hash_changes_nothing(self, profiled: Callable) -> None:
        resource = profiled()
        target = get_summary_target("resource", resource.id)
        assert save_summary_if_current(target, "0" * 64, GOOD, "m", "p") is False
        assert profile_of(resource).summary_text == ""

    def test_rejections_count_only_against_the_current_hash(self, profiled: Callable) -> None:
        resource = profiled()
        target = get_summary_target("resource", resource.id)
        record_rejection(target, target.profile.facts_hash)
        record_rejection(target, "0" * 64)
        assert profile_of(resource).summary_rejections == 1

    def test_new_facts_written_between_check_and_write_win(self, profiled: Callable) -> None:
        resource = profiled()
        target = get_summary_target("resource", resource.id)
        checked = target.profile.facts_hash
        # A sync pass writes newer facts meanwhile.
        ResourceProfile.objects.filter(resource=resource).update(
            facts_hash="n" * 64, summary_needed=True
        )

        assert save_summary_if_current(target, checked, GOOD, "m", "p") is False
        profile = profile_of(resource)
        assert (profile.summary_needed, profile.summary_text) == (True, "")


def url(level: str, item: Any) -> str:
    return f"/api/internal/qe/summaries/{level}/{getattr(item, 'id', item)}/"


def body(facts_hash: str, text: str = GOOD) -> Dict[str, str]:
    return {"facts_hash": facts_hash, "text": text, "model": "test/model", "prompt_version": "pv1"}


@pytest.mark.django_db
class TestSummaryEndpoints:
    def test_pending_shape_and_limit_cap(self, api: Callable, profiled: Callable) -> None:
        profiled()
        response = api().get("/api/internal/qe/summaries/pending/", {"limit": 1})
        assert response.status_code == 200
        [item] = response.json()
        assert set(item) == {"level", "id", "facts_hash", "facts"}
        assert api().get("/api/internal/qe/summaries/pending/", {"limit": 21}).status_code == 400

    def test_a_good_summary_is_stored_and_then_shown_labelled_generated(
        self, api: Callable, profiled: Callable
    ) -> None:
        resource = profiled()
        current = profile_of(resource).facts_hash

        assert api().put(url("resource", resource), body(current), format="json").status_code == 204

        view = (
            api()
            .get(f"/api/internal/qe/resources/{resource.id}/profile/", {"scope": "platform"})
            .json()
        )
        assert view["summary"]["text"] == GOOD and view["summary"]["generated"] is True
        assert str(resource.id) not in [
            i["id"] for i in api().get("/api/internal/qe/summaries/pending/").json()
        ]

    def test_a_dataset_summary_is_stored_too(self, api: Callable, profiled: Callable) -> None:
        resource = profiled()
        current = DatasetProfile.objects.get(dataset_id=resource.dataset_id).facts_hash
        response = api().put(
            url("dataset", resource.dataset_id), body(current, DATASET_GOOD), format="json"
        )
        assert response.status_code == 204, response.content
        # The table's figures are not dataset facts: a dataset summary can't use them.
        other = GOOD.replace("Counts", "Totals")
        assert (
            api()
            .put(url("dataset", resource.dataset_id), body(current, other), format="json")
            .status_code
            == 422
        )

    def test_a_stale_hash_is_409_and_stores_nothing(
        self, api: Callable, profiled: Callable
    ) -> None:
        resource = profiled()
        response = api().put(url("resource", resource), body("0" * 64), format="json")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "facts_changed"
        assert profile_of(resource).summary_text == ""

    def test_an_invented_number_is_422_listed_and_counted(
        self, api: Callable, profiled: Callable
    ) -> None:
        resource = profiled()
        current = profile_of(resource).facts_hash
        text = GOOD.replace("3 districts", "36 districts")

        response = api().put(url("resource", resource), body(current, text), format="json")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "untraced_numbers"
        assert response.json()["error"]["untraced_numbers"] == ["36"]
        assert profile_of(resource).summary_rejections == 1
        assert profile_of(resource).summary_text == ""

    def test_a_link_is_422_counted_and_not_stored(self, api: Callable, profiled: Callable) -> None:
        resource = profiled()
        current = profile_of(resource).facts_hash
        response = api().put(
            url("resource", resource), body(current, GOOD + " https://x.org"), format="json"
        )
        assert response.status_code == 422
        assert response.json()["error"]["problems"] == ["url"]
        # Counted, so an item whose summaries keep breaking the text rules stops being offered.
        assert profile_of(resource).summary_rejections == 1
        assert profile_of(resource).summary_text == ""

    def test_after_two_rejections_the_item_is_no_longer_offered(
        self, api: Callable, profiled: Callable
    ) -> None:
        resource = profiled()
        current = profile_of(resource).facts_hash
        for _ in range(2):
            api().put(
                url("resource", resource), body(current, GOOD.replace("19", "91")), format="json"
            )
        pending = api().get("/api/internal/qe/summaries/pending/").json()
        assert str(resource.id) not in [i["id"] for i in pending]

    def test_a_write_for_an_ineligible_item_is_404_and_stores_nothing(
        self, api: Callable, profiled: Callable
    ) -> None:
        resource = profiled()
        current = profile_of(resource).facts_hash
        Dataset.objects.filter(pk=resource.dataset_id).update(
            access_type=DatasetAccessType.RESTRICTED
        )

        assert api().put(url("resource", resource), body(current), format="json").status_code == 404
        assert (
            api().put(url("dataset", resource.dataset_id), body(current), format="json").status_code
            == 404
        )
        assert api().put(url("tables", resource), body(current), format="json").status_code == 404
        assert profile_of(resource).summary_text == ""

    def test_numbers_are_never_checked_on_a_stale_hash(
        self, api: Callable, profiled: Callable
    ) -> None:
        resource = profiled()
        with mock.patch("api.views.query_engine.summary_views.find_untraced_numbers") as check:
            api().put(url("resource", resource), body("0" * 64, GOOD), format="json")
        check.assert_not_called()

    def test_summary_text_and_tokens_never_reach_the_info_logs(
        self, api: Callable, profiled: Callable, caplog: Any
    ) -> None:
        caplog.set_level(logging.INFO)
        resource = profiled()
        current = profile_of(resource).facts_hash
        api().put(url("resource", resource), body(current, GOOD.replace("19", "91")), format="json")
        api().put(url("resource", resource), body(current), format="json")
        assert "Counts of cases" not in caplog.text
        assert "service-token" not in caplog.text
        assert "qe_request_refused" in caplog.text and "qe_summary_stored" in caplog.text
