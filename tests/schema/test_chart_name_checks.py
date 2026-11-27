"""Chart and chart image names: no database error text, no blank names (#325).

Root cause: chart mutations save without `full_clean`, so the 50-character name
and 1000-character description columns were only enforced by Postgres, whose
own error text ("value too long for type character varying(50)") reached the
client. Names were only checked with `if name:`, so "   " was saved.

Fix: `_check_chart_text` / `_checked_image_name` run before anything is saved:
names and descriptions are trimmed, too long ones are refused with a fixed
message, and a blank name is refused when it would replace a saved one. A chart
that is already blank may be sent back as it is, because the chart editor resends
the current name with every other change.

SQLite does not enforce varchar lengths, so these tests check the message and
that nothing changed, not the Postgres error.
"""

import types

import pytest
from django.test import RequestFactory

from api.models import (
    Dataset,
    Organization,
    Resource,
    ResourceChartDetails,
    ResourceChartImage,
)
from api.schema.schema import schema
from authorization.models import User

CHART = (
    "... on TypeResourceChart { id name description } ... on OperationInfo { messages { message } }"
)
IMAGE = "... on TypeResourceChartImage { id name } ... on OperationInfo { messages { message } }"

EDIT = f"mutation ($i: ResourceChartInput!) {{ editResourceChart(chartInput: $i) {{ {CHART} }} }}"
CREATE = (
    f"mutation ($i: ResourceChartInput!) {{ createResourceChart(chartInput: $i) {{ {CHART} }} }}"
)
CREATE_IMAGE = f"mutation ($i: ResourceChartImageInput!) {{ createResourceChartImage(input: $i) {{ {IMAGE} }} }}"
UPDATE_IMAGE = (
    "mutation ($i: ResourceChartImageInputPartial!) "
    f"{{ updateResourceChartImage(input: $i) {{ {IMAGE} }} }}"
)


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


def error(result):
    assert result.errors, f"expected an error, got {result.data}"
    return result.errors[0].message


@pytest.fixture
def world(db):
    owner = User.objects.create(username="owner", keycloak_id="owner")
    org = Organization.objects.create(name="Org", description="o", slug="org")
    dataset = Dataset.objects.create(
        title="Draft", slug="draft", description="d", user=owner, organization=org
    )
    resource = Resource.objects.create(name="d.csv", dataset=dataset)
    return types.SimpleNamespace(
        owner=owner,
        dataset=dataset,
        resource=resource,
        chart=ResourceChartDetails.objects.create(
            name="Rainfall", description="Old", resource=resource
        ),
        image=ResourceChartImage.objects.create(name="Map", dataset=dataset),
    )


def edit(world, **fields):
    chart_input = {"chartId": str(world.chart.id), "resource": str(world.resource.id), **fields}
    return run(world.owner, EDIT, i=chart_input)


def update_image(world, **fields):
    image_input = {"id": str(world.image.id), "dataset": str(world.dataset.id), **fields}
    return run(world.owner, UPDATE_IMAGE, i=image_input)


# --- editResourceChart ---


def test_edit_refuses_a_name_over_50_characters(world):
    message = error(edit(world, name="n" * 51))
    assert message == "Chart name cannot be longer than 50 characters."
    world.chart.refresh_from_db()
    assert world.chart.name == "Rainfall"


def test_edit_saves_a_name_of_exactly_50_characters(world):
    result = edit(world, name="n" * 50)
    assert not result.errors
    world.chart.refresh_from_db()
    assert world.chart.name == "n" * 50


@pytest.mark.parametrize("name", ["   ", "", "\t\n"])
def test_edit_refuses_a_blank_name(world, name):
    assert error(edit(world, name=name)) == "Chart name cannot be blank."
    world.chart.refresh_from_db()
    assert world.chart.name == "Rainfall"


def test_edit_trims_the_name_and_checks_the_trimmed_length(world):
    result = edit(world, name="  " + "n" * 50 + "  ")
    assert not result.errors
    world.chart.refresh_from_db()
    assert world.chart.name == "n" * 50


def test_edit_without_a_name_keeps_the_saved_one(world):
    result = edit(world, type="LINE")
    assert not result.errors
    world.chart.refresh_from_db()
    assert world.chart.name == "Rainfall"


def test_an_already_blank_chart_can_still_be_edited(world):
    """The editor resends the saved name with every change; a blank one must not block it."""
    ResourceChartDetails.objects.filter(id=world.chart.id).update(name="")
    result = edit(world, name="", type="LINE")
    assert not result.errors
    world.chart.refresh_from_db()
    assert world.chart.chart_type == "LINE"


def test_edit_refuses_a_description_over_1000_characters(world):
    message = error(edit(world, description="d" * 1001))
    assert message == "Chart description cannot be longer than 1000 characters."
    world.chart.refresh_from_db()
    assert world.chart.description == "Old"


def test_edit_refusal_happens_before_the_resource_is_changed(world):
    other = Resource.objects.create(name="o.csv", dataset=world.dataset)
    chart_input = {"chartId": str(world.chart.id), "resource": str(other.id), "name": "n" * 51}
    assert error(run(world.owner, EDIT, i=chart_input))
    world.chart.refresh_from_db()
    assert world.chart.resource_id == world.resource.id


def test_edit_without_chart_id_creates_nothing_when_refused(world):
    before = ResourceChartDetails.objects.count()
    result = run(world.owner, EDIT, i={"resource": str(world.resource.id), "name": "n" * 51})
    assert error(result)
    assert ResourceChartDetails.objects.count() == before


# --- createResourceChart ---


def test_create_refuses_a_long_name_and_creates_nothing(world):
    before = ResourceChartDetails.objects.count()
    result = run(world.owner, CREATE, i={"resource": str(world.resource.id), "name": "n" * 51})
    assert error(result) == "Chart name cannot be longer than 50 characters."
    assert ResourceChartDetails.objects.count() == before


def test_create_with_a_blank_name_gets_the_default_name(world):
    result = run(world.owner, CREATE, i={"resource": str(world.resource.id), "name": "   "})
    assert not result.errors
    assert result.data["createResourceChart"]["name"].startswith("New chart ")


def test_create_trims_name_and_description(world):
    chart_input = {"resource": str(world.resource.id), "name": " Rain ", "description": " d "}
    result = run(world.owner, CREATE, i=chart_input)
    assert not result.errors
    assert result.data["createResourceChart"]["name"] == "Rain"
    assert result.data["createResourceChart"]["description"] == "d"


# --- chart images ---


def test_image_update_refuses_a_long_name(world):
    assert (
        error(update_image(world, name="n" * 51))
        == "Chart name cannot be longer than 50 characters."
    )
    world.image.refresh_from_db()
    assert world.image.name == "Map"


@pytest.mark.parametrize("name", ["   ", ""])
def test_image_update_refuses_a_blank_name(world, name):
    assert error(update_image(world, name=name)) == "Chart name cannot be blank."
    world.image.refresh_from_db()
    assert world.image.name == "Map"


def test_image_update_trims_the_name(world):
    result = update_image(world, name="  Rain map  ")
    assert not result.errors
    world.image.refresh_from_db()
    assert world.image.name == "Rain map"


def test_image_update_without_a_name_keeps_the_saved_one(world):
    assert not update_image(world).errors
    world.image.refresh_from_db()
    assert world.image.name == "Map"


def test_image_create_refuses_a_long_name_and_creates_nothing(world):
    before = ResourceChartImage.objects.count()
    result = run(world.owner, CREATE_IMAGE, i={"dataset": str(world.dataset.id), "name": "n" * 51})
    assert error(result) == "Chart name cannot be longer than 50 characters."
    assert ResourceChartImage.objects.count() == before


def test_image_create_with_a_blank_name_gets_the_default_name(world):
    result = run(world.owner, CREATE_IMAGE, i={"dataset": str(world.dataset.id), "name": "   "})
    assert not result.errors
    assert result.data["createResourceChartImage"]["name"].startswith("New resource_chart_image ")
