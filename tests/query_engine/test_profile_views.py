"""Layer 2: the profile views stay within their budget and say what they left out (V1, V3)."""

import json
import types
import uuid
from typing import Any, Callable, Dict, List

import pytest

from api.models import Resource, ResourceSchema
from api.services.query_engine.profile_views import (
    MAX_VIEW_COLUMNS,
    VIEW_BUDGET_CHARS,
    current_summary,
    dataset_profile_view,
    resource_profile_view,
)


def wide_stats(count: int) -> Dict[str, Any]:
    columns: List[Dict[str, Any]] = [
        {
            "name": f"Indicator number {index} for women aged 15 to 49 (%)",
            "profiled": index < 300,
            "kind": "numeric",
            "role": "measure",
            "min": 0.5,
            "max": 99.5,
            "null_pct": 1.5,
        }
        for index in range(count)
    ]
    return {"row_count": 700, "columns": columns, "layout": "long", "analysable": True}


def profile(stats: Dict[str, Any], **summary: Any) -> types.SimpleNamespace:
    fields = {
        "stats": stats,
        "status": "READY",
        "facts_hash": "f1",
        "summary_text": "",
        "summary_facts_hash": "",
        "summary_model": "",
        "summary_generated_at": None,
    }
    fields.update(summary)
    return types.SimpleNamespace(**fields)


def size(view: Dict[str, Any]) -> int:
    return len(json.dumps(view, ensure_ascii=False))


@pytest.mark.django_db
class TestResourceView:
    def test_a_300_column_table_stays_within_budget_and_counts_what_it_left_out(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        for column in wide_stats(320)["columns"]:
            ResourceSchema.objects.create(
                resource=resource,
                field_name=column["name"],
                format="NUMBER",
                description="Share of women in the district " * 8,
            )

        view = resource_profile_view(resource, profile(wide_stats(320)))

        assert size(view) <= VIEW_BUDGET_CHARS
        assert len(view["columns"]) <= MAX_VIEW_COLUMNS
        assert view["columns_omitted"] == 320 - len(view["columns"])
        assert view["column_count"] == 320

    def test_named_columns_come_back_in_detail(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        stats = wide_stats(3)
        name = stats["columns"][1]["name"]

        view = resource_profile_view(resource, profile(stats), columns=[name, "nope"])

        assert [c["name"] for c in view["columns"]] == [name]
        assert view["columns"][0]["min"] == 0.5
        assert view["unknown_columns"] == ["nope"]

    def test_placeholder_descriptions_are_dropped_and_publisher_text_is_marked(
        self, make_dataset: Callable, make_resource: Callable
    ) -> None:
        resource = make_resource(make_dataset())
        stats = wide_stats(1)
        name = stats["columns"][0]["name"]
        ResourceSchema.objects.create(
            resource=resource,
            field_name=name,
            format="NUMBER",
            description=f"Description of column {name}",
        )

        view = resource_profile_view(resource, profile(stats))

        assert "description" not in view["columns"][0]
        assert "untrusted" in view["untrusted_text"] or "not instructions" in view["untrusted_text"]


class TestCurrentSummary:
    def test_shown_only_when_written_from_the_current_facts(self) -> None:
        fresh = profile({}, summary_text="Covers 3 districts.", summary_facts_hash="f1")
        stale = profile({}, summary_text="Covers 3 districts.", summary_facts_hash="old")

        assert current_summary(fresh)["generated"] is True
        assert current_summary(fresh)["text"] == "Covers 3 districts."
        assert current_summary(stale) is None
        assert current_summary(None) is None


@pytest.mark.django_db
def test_a_dataset_with_400_tables_lists_50_and_covers_all_of_them(make_dataset: Callable) -> None:
    dataset = make_dataset("District fact sheets")
    tables = []
    for index in range(400):
        resource = types.SimpleNamespace(
            id=uuid.uuid4(),
            name=f"District {index:03d} fact sheet",
            description="NFHS-5 indicators",
        )
        year = "2015-16" if index < 399 else "2019-20"
        stats = {
            "row_count": 100,
            "analysable": True,
            "columns": [
                {
                    "name": "Round",
                    "profiled": True,
                    "time": {"kind": "fiscal_year", "values": [year]},
                }
            ],
        }
        tables.append((resource, stats))

    view = dataset_profile_view(dataset, tables)

    assert len(view["tables"]) == 50
    assert view["tables_omitted"] == 350
    assert view["coverage"]["years"] == ["2015-16", "2019-20"]
    assert size(view) <= VIEW_BUDGET_CHARS
    assert view["tables"][0]["resource_id"] == str(tables[0][0].id)
