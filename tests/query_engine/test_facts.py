"""Layer 2: the facts bundle and its hash (V2)."""

import json
from typing import Any, Callable, Dict

import pytest

from api.models import Resource, ResourceSchema, Tag
from api.services.query_engine.facts import facts_hash, resource_facts


def stats(**changes: Any) -> Dict[str, Any]:
    base = {
        "row_count": 3,
        "layout": "long",
        "analysable": True,
        "columns": [
            {
                "name": "IMR (%)",
                "profiled": True,
                "kind": "numeric",
                "role": "measure",
                "min": 22.0,
                "max": 40.0,
                "placeholder_count": 0,
            }
        ],
    }
    base.update(changes)
    return base


@pytest.fixture
def table(make_dataset: Callable, make_resource: Callable) -> Resource:
    resource = make_resource(make_dataset("Child health"), name="Indicators")
    ResourceSchema.objects.create(
        resource=resource, field_name="IMR (%)", format="NUMBER", description="Infant mortality"
    )
    return Resource.objects.select_related("dataset__organization").get(pk=resource.pk)


@pytest.mark.django_db
class TestFactsHash:
    def test_ignores_key_order(self) -> None:
        assert facts_hash({"a": 1, "b": [1, 2]}) == facts_hash({"b": [1, 2], "a": 1})

    def test_carries_no_ids_or_timestamps(self, table: Resource) -> None:
        text = json.dumps(resource_facts(table, stats()))
        for value in (str(table.id), str(table.dataset.id), str(table.resourcedatatable.id)):
            assert value not in text
        assert table.created.isoformat()[:19] not in text

    def test_is_stable_for_the_same_inputs(self, table: Resource) -> None:
        assert facts_hash(resource_facts(table, stats())) == facts_hash(
            resource_facts(table, stats())
        )

    def test_changes_when_a_description_changes(self, table: Resource) -> None:
        before = facts_hash(resource_facts(table, stats()))
        ResourceSchema.objects.filter(resource=table).update(description="Deaths per 1,000")
        assert facts_hash(resource_facts(table, stats())) != before

    def test_changes_when_a_name_or_tag_changes(self, table: Resource) -> None:
        before = facts_hash(resource_facts(table, stats()))
        table.name = "Indicators 2019"
        renamed = facts_hash(resource_facts(table, stats()))
        table.dataset.tags.add(Tag.objects.create(value="anaemia"))
        tagged = facts_hash(resource_facts(table, stats()))
        assert len({before, renamed, tagged}) == 3

    def test_changes_when_a_stat_changes(self, table: Resource) -> None:
        assert facts_hash(resource_facts(table, stats())) != facts_hash(
            resource_facts(table, stats(row_count=4))
        )

    def test_column_facts_carry_description_unit_and_range(self, table: Resource) -> None:
        facts = resource_facts(table, stats())
        assert facts["columns"] == [
            {
                "name": "IMR (%)",
                "description": "Infant mortality",
                "kind": "numeric",
                "role": "measure",
                "unit": "%",
                "min": 22.0,
                "max": 40.0,
            }
        ]
        assert facts["dataset"]["title"] == "Child health"
        assert facts["dataset"]["organization"] == "Health Org"
