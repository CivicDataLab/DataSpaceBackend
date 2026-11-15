"""Layer 4 (real Postgres data database): POST resources/<id>/query/ (QRY, LEAK2 for queries).

Every refused table is real and profiled, so the query would succeed without
the corpus and scope checks.
"""

from typing import Any, Callable, Dict

import pytest

from api.models import Resource, ResourceProfile
from api.services.query_engine.geography_match import GeographyIndex
from api.services.query_engine.profiles import (
    build_resource_stats,
    save_resource_profile_if_current,
)
from api.utils.enums import DatasetAccessType, DatasetStatus, DatasetType
from tests.data_index.support import DATA_DB, uses_data_db

SPEC: Dict[str, Any] = {
    "scope": "platform",
    "group_by": ["District"],
    "measures": [{"fn": "avg", "column": "IMR (%)", "as": "imr"}],
    "order_by": [{"by": "imr", "dir": "desc"}],
}


def url(resource: Any) -> str:
    return f"/api/internal/qe/resources/{getattr(resource, 'id', resource)}/query/"


@pytest.fixture
def profiled(make_table_resource: Callable, geography: GeographyIndex) -> Callable[..., Resource]:
    def make(csv: str = "district_health.csv", **dataset_changes: Any) -> Resource:
        resource = make_table_resource(csv)
        if dataset_changes:
            type(resource.dataset).objects.filter(pk=resource.dataset_id).update(**dataset_changes)
        stats = build_resource_stats(resource, geography)
        assert save_resource_profile_if_current(resource, resource.resourcedatatable.id, stats)
        ResourceProfile.objects.filter(resource=resource).update(facts_hash="f" * 64)
        return resource

    return make


@uses_data_db
def test_an_aggregate_returns_rows_sql_units_spec_and_provenance(
    api: Callable, profiled: Callable
) -> None:
    resource = profiled()

    response = api().post(url(resource), SPEC, format="json")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["columns"] == ["District", "imr"]
    assert body["rows"] == [["Dibrugarh", 39.0], ["Kamrup", 31.5], ["Kamrup Metro", 23.5]]
    assert body["units"] == {"imr": "%"}
    assert body["sql"].startswith('SELECT "g0", "imr" FROM (SELECT "District" AS "g0"')
    assert '"IMR (%)"' in body["sql"] and "'Total'" in body["sql"]
    assert body["query_spec"]["measures"] == [{"fn": "avg", "column": "IMR (%)", "as": "imr"}]
    assert body["provenance"] == {
        "dataset_id": str(resource.dataset_id),
        "resource_id": str(resource.id),
        "data_table_id": str(resource.resourcedatatable.id),
        "facts_hash": "f" * 64,
    }
    assert any("Total" in note for note in body["notes"])


@uses_data_db
def test_numeric_text_reports_ignored_rows(api: Callable, profiled: Callable) -> None:
    resource = profiled("numeric_text.csv")
    spec = {"scope": "platform", "measures": [{"fn": "sum", "column": "Count", "as": "total"}]}

    body = api().post(url(resource), spec, format="json").json()

    assert body["rows"] == [[123468.5]]
    assert body["non_numeric_rows_ignored"] == {"total": 2}
    assert "qe_patterns" in body["sql"]


@uses_data_db
def test_a_bad_spec_is_400(api: Callable, profiled: Callable) -> None:
    resource = profiled()
    response = api().post(url(resource), {**SPEC, "group_by": ["Nope"]}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_query_spec"


@uses_data_db
def test_a_slow_query_is_422(api: Callable, profiled: Callable, settings: Any) -> None:
    resource = profiled()
    settings.QE_QUERY_TIMEOUT_MS = 1
    from django.db import connections

    with connections[DATA_DB].cursor() as cursor:
        cursor.execute(
            f'INSERT INTO "{resource.resourcedatatable.table_name}" ("District", "IMR (%)") '
            "SELECT 'D' || g, g FROM generate_series(1, 300000) g"
        )
    response = api().post(url(resource), SPEC, format="json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "query_too_slow"


@uses_data_db
def test_a_table_dropped_under_the_profile_is_409(api: Callable, profiled: Callable) -> None:
    resource = profiled()
    from django.db import connections

    with connections[DATA_DB].cursor() as cursor:
        cursor.execute(f'DROP TABLE "{resource.resourcedatatable.table_name}"')
    response = api().post(url(resource), SPEC, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "data_refreshing"


@uses_data_db
def test_a_stale_profile_is_409(api: Callable, profiled: Callable) -> None:
    import uuid

    resource = profiled()
    ResourceProfile.objects.filter(resource=resource).update(data_table_id=uuid.uuid4())
    response = api().post(url(resource), SPEC, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "profile_not_ready"


@uses_data_db
def test_a_table_without_numbers_is_422(
    api: Callable, make_table_resource: Callable, geography: GeographyIndex
) -> None:
    resource = make_table_resource(b"District,Remarks\nKamrup,good\nNagaon,fair\n")
    stats = build_resource_stats(resource, geography)
    save_resource_profile_if_current(resource, resource.resourcedatatable.id, stats)

    response = api().post(
        url(resource), {"scope": "platform", "measures": [{"fn": "count"}]}, format="json"
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "not_analysable",
        "message": "This table can't be analysed.",
        "reasons": ["no_numeric_measure"],
    }


@uses_data_db
@pytest.mark.parametrize(
    "changes",
    [
        {"status": DatasetStatus.DRAFT},
        {"status": DatasetStatus.ARCHIVED},
        {"access_type": DatasetAccessType.PRIVATE},
        {"access_type": DatasetAccessType.RESTRICTED},
        {"dataset_type": DatasetType.PROMPT},
    ],
    ids=["draft", "archived", "private", "restricted", "prompt"],
)
def test_an_ineligible_table_is_404(api: Callable, profiled: Callable, changes: dict) -> None:
    resource = profiled(**changes)
    assert api().post(url(resource), SPEC, format="json").status_code == 404


@uses_data_db
def test_an_inactive_table_is_404(api: Callable, profiled: Callable) -> None:
    resource = profiled()
    Resource.objects.filter(pk=resource.pk).update(is_active=False)
    assert api().post(url(resource), SPEC, format="json").status_code == 404


@uses_data_db
def test_a_table_outside_the_collaborative_is_404_inside_it(
    api: Callable, profiled: Callable, make_collaborative: Callable
) -> None:
    resource = profiled()
    fem = make_collaborative("FemHealth", datasets=[])
    body = {**SPEC, "scope": f"collaborative:{fem.public_id}"}

    assert api().post(url(resource), body, format="json").status_code == 404
    fem.datasets.add(resource.dataset)
    assert api().post(url(resource), body, format="json").status_code == 200


@uses_data_db
def test_a_scope_nested_in_the_spec_is_400(
    api: Callable, profiled: Callable, make_collaborative: Callable
) -> None:
    resource = profiled()
    fem = make_collaborative("FemHealth", datasets=[resource.dataset])
    body = {
        **SPEC,
        "scope": f"collaborative:{fem.public_id}",
        "filters": [{"column": "District", "op": "eq", "value": "Kamrup", "scope": "platform"}],
    }

    response = api().post(url(resource), body, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_query_spec"


@uses_data_db
def test_platform_scope_with_sectors_hides_tables_of_other_sectors(
    api: Callable, profiled: Callable, settings: Any, make_sector: Callable
) -> None:
    make_sector("Climate Action")
    resource = profiled()
    settings.QE_PLATFORM_SECTORS = ["climate-action"]

    assert api().post(url(resource), SPEC, format="json").status_code == 404


@uses_data_db
def test_a_change_in_a_percentage_is_in_percentage_points(
    api: Callable, profiled: Callable
) -> None:
    resource = profiled()
    spec = {
        "scope": "platform",
        "measures": [{"fn": "avg", "column": "IMR (%)", "as": "imr"}],
        "compare": {"column": "Survey round", "base": "2015-16", "target": "2019-20"},
    }

    units = api().post(url(resource), spec, format="json").json()["units"]

    assert units["imr__base"] == "%"
    assert units["imr__change"] == "percentage points"
    assert units["imr__pct_change"] == "%"
