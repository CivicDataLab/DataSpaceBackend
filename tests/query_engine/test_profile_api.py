"""Layer 4: GET datasets/<id>/profile/ and resources/<id>/profile/ (shape, 409, LEAK2, LEAK-SCOPE).

Every refused item has a READY profile, so without the corpus and scope
checks the endpoint would answer 200 — each 404 here proves a guard.
"""

import uuid
from typing import Any, Callable, Dict

import pytest

from api.models import Resource, ResourceProfile, ResourceSchema
from api.services.query_engine.profiles import save_resource_profile_if_current
from api.utils.enums import DatasetAccessType, DatasetStatus, DatasetType

STATS: Dict[str, Any] = {
    "row_count": 8,
    "layout": "long",
    "year_columns": [],
    "analysable": True,
    "not_analysable_reasons": [],
    "notes": [],
    "stats_complete": True,
    "columns": [
        {
            "name": "District",
            "profiled": True,
            "kind": "text",
            "role": "dimension",
            "top_values": [["Kamrup", 2]],
        },
        {
            "name": "IMR (%)",
            "profiled": True,
            "kind": "numeric",
            "role": "measure",
            "min": 22.0,
            "max": 40.0,
        },
    ],
}


def ready(resource: Resource) -> Resource:
    assert save_resource_profile_if_current(resource, resource.resourcedatatable.id, STATS)
    return resource


def resource_url(resource_id: Any) -> str:
    return f"/api/internal/qe/resources/{resource_id}/profile/"


def dataset_url(dataset_id: Any) -> str:
    return f"/api/internal/qe/datasets/{dataset_id}/profile/"


@pytest.mark.django_db
class TestResourceProfile:
    def test_returns_the_compact_view(
        self, api: Callable, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = ready(make_resource(make_dataset()))
        ResourceSchema.objects.create(
            resource=resource, field_name="IMR (%)", format="NUMBER", description="Infant mortality"
        )

        response = api().get(resource_url(resource.id), {"scope": "platform"})

        assert response.status_code == 200
        body = response.json()
        assert body["resource_id"] == str(resource.id)
        assert (body["status"], body["row_count"], body["analysable"]) == ("READY", 8, True)
        assert body["columns"][1] == {
            "name": "IMR (%)",
            "kind": "numeric",
            "role": "measure",
            "unit": "%",
            "description": "Infant mortality",
            "min": 22.0,
            "max": 40.0,
        }
        assert body["summary"] is None

    def test_named_columns_come_back_in_detail(
        self, api: Callable, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = ready(make_resource(make_dataset()))

        response = api().get(
            resource_url(resource.id), {"scope": "platform", "columns": ["IMR (%)", "Missing"]}
        )

        body = response.json()
        assert [c["name"] for c in body["columns"]] == ["IMR (%)"]
        assert body["unknown_columns"] == ["Missing"]

    def test_more_than_20_columns_is_400(
        self, api: Callable, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = ready(make_resource(make_dataset()))
        response = api().get(
            resource_url(resource.id),
            {"scope": "platform", "columns": [f"c{i}" for i in range(21)]},
        )
        assert response.status_code == 400
        assert response.json()["error"]["fields"] == {"columns": ["max_length"]}

    def test_no_profile_yet_is_409(
        self, api: Callable, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        response = api().get(resource_url(resource.id), {"scope": "platform"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "profile_not_ready"

    def test_a_profile_of_the_previous_upload_is_409(
        self, api: Callable, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = ready(make_resource(make_dataset()))
        ResourceProfile.objects.filter(resource=resource).update(data_table_id=uuid.uuid4())
        assert api().get(resource_url(resource.id), {"scope": "platform"}).status_code == 409

    def test_missing_scope_is_400(
        self, api: Callable, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = ready(make_resource(make_dataset()))
        assert api().get(resource_url(resource.id)).status_code == 400

    def test_an_unknown_id_is_404(self, api: Callable) -> None:
        assert api().get(resource_url(uuid.uuid4()), {"scope": "platform"}).status_code == 404


@pytest.mark.django_db
class TestDatasetProfile:
    def test_returns_tables_other_resources_and_coverage(
        self, api: Callable, make_dataset: Callable, make_resource: Callable
    ) -> None:
        dataset = make_dataset("Child health")
        table = ready(make_resource(dataset, name="Indicators"))
        make_resource(dataset, name="Methodology", with_table=False)

        response = api().get(dataset_url(dataset.id), {"scope": "platform"})

        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Child health"
        assert [(t["resource_id"], t["name"], t["analysable"]) for t in body["tables"]] == [
            (str(table.id), "Indicators", True)
        ]
        assert body["other_resources"] == [{"name": "Methodology", "format": "file"}]
        assert (body["tables_omitted"], body["others_omitted"]) == (0, 0)


INELIGIBLE = [
    ({"status": DatasetStatus.DRAFT}, {}),
    ({"status": DatasetStatus.ARCHIVED}, {}),
    ({"access_type": DatasetAccessType.PRIVATE}, {}),
    ({"access_type": DatasetAccessType.RESTRICTED}, {}),
    ({"dataset_type": DatasetType.PROMPT}, {}),
    ({}, {"is_active": False}),
]


@pytest.mark.django_db
class TestLeaks:
    @pytest.mark.parametrize(
        "dataset_changes,resource_changes",
        INELIGIBLE,
        ids=["draft", "archived", "private", "restricted", "prompt", "inactive"],
    )
    def test_an_ineligible_table_is_404_even_with_a_ready_profile(
        self,
        api: Callable,
        make_dataset: Callable,
        make_resource: Callable,
        dataset_changes: dict,
        resource_changes: dict,
    ) -> None:
        dataset = make_dataset(**dataset_changes)
        resource = ready(make_resource(dataset, **resource_changes))

        assert api().get(resource_url(resource.id), {"scope": "platform"}).status_code == 404
        if dataset_changes:
            assert api().get(dataset_url(dataset.id), {"scope": "platform"}).status_code == 404

    def test_a_table_with_no_data_table_is_404_not_409(
        self, api: Callable, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = ready(make_resource(make_dataset()))
        from api.models import ResourceDataTable

        ResourceDataTable.objects.filter(resource=resource).delete()
        assert api().get(resource_url(resource.id), {"scope": "platform"}).status_code == 404

    def test_a_dataset_outside_the_collaborative_is_404_inside_it(
        self,
        api: Callable,
        make_dataset: Callable,
        make_resource: Callable,
        make_collaborative: Callable,
    ) -> None:
        inside = ready(make_resource(make_dataset("Anaemia")))
        outside = ready(make_resource(make_dataset("Rainfall")))
        fem = make_collaborative("FemHealth", datasets=[inside.dataset])
        scope = {"scope": f"collaborative:{fem.public_id}"}

        assert api().get(resource_url(inside.id), scope).status_code == 200
        assert api().get(resource_url(outside.id), scope).status_code == 404
        assert api().get(dataset_url(outside.dataset_id), scope).status_code == 404
        # The same table is fine in platform scope.
        assert api().get(resource_url(outside.id), {"scope": "platform"}).status_code == 200

    def test_platform_scope_with_sectors_hides_other_sectors(
        self,
        api: Callable,
        settings: Any,
        make_dataset: Callable,
        make_resource: Callable,
        make_sector: Callable,
    ) -> None:
        climate = make_sector("Climate Action")
        kept = ready(make_resource(make_dataset("Rainfall", sectors=[climate])))
        other = ready(make_resource(make_dataset("Anaemia")))
        settings.QE_PLATFORM_SECTORS = ["climate-action"]

        assert api().get(resource_url(kept.id), {"scope": "platform"}).status_code == 200
        assert api().get(resource_url(other.id), {"scope": "platform"}).status_code == 404
        assert api().get(dataset_url(other.dataset_id), {"scope": "platform"}).status_code == 404

    def test_an_unpublished_collaborative_is_404_on_both_endpoints(
        self,
        api: Callable,
        make_dataset: Callable,
        make_resource: Callable,
        make_collaborative: Callable,
    ) -> None:
        resource = ready(make_resource(make_dataset()))
        draft = make_collaborative(status="DRAFT", datasets=[resource.dataset])
        scope = {"scope": f"collaborative:{draft.public_id}"}

        assert api().get(resource_url(resource.id), scope).status_code == 404
        assert api().get(dataset_url(resource.dataset_id), scope).status_code == 404


@pytest.mark.django_db
def test_the_dataset_view_carries_each_tables_current_summary(
    api: Callable, make_dataset: Callable, make_resource: Callable
) -> None:
    dataset = make_dataset("FemHealth indicators")
    fresh = ready(make_resource(dataset, name="Anaemia"))
    stale = ready(make_resource(dataset, name="Stunting"))
    ResourceProfile.objects.filter(resource=fresh).update(
        facts_hash="f1", summary_facts_hash="f1", summary_text="Anaemia among women. " * 20
    )
    ResourceProfile.objects.filter(resource=stale).update(
        facts_hash="new", summary_facts_hash="old", summary_text="Written for older data."
    )

    tables = {
        t["name"]: t
        for t in api().get(dataset_url(dataset.id), {"scope": "platform"}).json()["tables"]
    }

    summary = tables["Anaemia"]["summary"]
    assert summary["generated"] is True and summary["text"].startswith("Anaemia among women.")
    assert len(summary["text"]) <= 200
    assert tables["Stunting"]["summary"] is None
