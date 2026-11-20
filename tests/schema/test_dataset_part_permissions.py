"""Charts, chart images, access models and prompt file
details need edit rights on their dataset; drafts' ones are hidden from people
who cannot see the draft."""

import types
import uuid

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from api.models import (
    AccessModel,
    Dataset,
    Organization,
    PromptResource,
    Resource,
    ResourceChartDetails,
    ResourceChartImage,
    ResourceSchema,
)
from api.schema.schema import schema
from authorization.models import DatasetPermission, OrganizationMembership, Role, User


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def world(db):
    org = Organization.objects.create(name="Org", description="o", slug="org")
    other_org = Organization.objects.create(name="Other", description="o", slug="other-org")
    editor_role = Role.objects.create(name="editor", can_view=True, can_add=True, can_change=True)
    viewer_role = Role.objects.create(name="viewer", can_view=True)
    users = {
        name: User.objects.create(username=name, keycloak_id=name)
        for name in ["owner", "editor", "viewer", "outsider", "shared"]
    }
    users["admin"] = User.objects.create(username="admin", keycloak_id="admin", is_superuser=True)
    OrganizationMembership.objects.create(user=users["editor"], organization=org, role=editor_role)
    OrganizationMembership.objects.create(user=users["viewer"], organization=org, role=viewer_role)
    OrganizationMembership.objects.create(
        user=users["outsider"], organization=other_org, role=editor_role
    )
    draft = Dataset.objects.create(
        title="Draft", slug="draft", description="d", user=users["owner"], organization=org
    )
    published = Dataset.objects.create(
        title="Pub",
        slug="pub",
        description="d",
        user=users["owner"],
        organization=org,
        status="PUBLISHED",
    )
    # The outsider's own dataset, for "move it into my dataset" attempts.
    theirs = Dataset.objects.create(
        title="Theirs",
        slug="theirs",
        description="d",
        user=users["outsider"],
        organization=other_org,
    )
    DatasetPermission.objects.create(user=users["shared"], dataset=draft, role=editor_role)
    draft_res = Resource.objects.create(name="d.csv", dataset=draft)
    pub_res = Resource.objects.create(name="p.csv", dataset=published)
    their_res = Resource.objects.create(name="t.csv", dataset=theirs)
    return types.SimpleNamespace(
        users=users,
        draft=draft,
        published=published,
        theirs=theirs,
        draft_res=draft_res,
        pub_res=pub_res,
        their_res=their_res,
        draft_chart=ResourceChartDetails.objects.create(name="dc", resource=draft_res),
        pub_chart=ResourceChartDetails.objects.create(name="pc", resource=pub_res),
        draft_image=ResourceChartImage.objects.create(name="di", dataset=draft),
        pub_image=ResourceChartImage.objects.create(name="pi", dataset=published),
        draft_am=AccessModel.objects.create(name="da", dataset=draft),
        pub_am=AccessModel.objects.create(name="pa", dataset=published),
    )


def user_for(world, who):
    return AnonymousUser() if who == "anonymous" else world.users[who]


def denied(result):
    """A permission refusal, as a top-level error or a handled OperationInfo."""
    text = str(result.errors) if result.errors else str(result.data)
    return "permission" in text


def u(ids):
    return {k: str(v) for k, v in ids.items()}


CHART = "... on TypeResourceChart { id } ... on OperationInfo { messages { message } }"
IMAGE = "... on TypeResourceChartImage { id } ... on OperationInfo { messages { message } }"
AM = "... on TypeAccessModel { id } ... on OperationInfo { messages { message } }"

# (query, variables from world, check the object is untouched afterwards)
MUTATIONS = {
    "addResourceChart": (
        f"mutation ($r: UUID!) {{ addResourceChart(resource: $r) {{ {CHART} }} }}",
        lambda w: {"r": w.pub_res.id},
    ),
    "createResourceChart": (
        f"mutation ($r: UUID!) {{ createResourceChart(chartInput: {{resource: $r}}) {{ {CHART} }} }}",
        lambda w: {"r": w.pub_res.id},
    ),
    "editResourceChart": (
        f"""mutation ($c: UUID!, $r: UUID!) {{
          editResourceChart(chartInput: {{chartId: $c, resource: $r, name: "x"}}) {{ {CHART} }}
        }}""",
        lambda w: {"c": w.pub_chart.id, "r": w.pub_res.id},
    ),
    "deleteResourceChart": (
        "mutation ($c: UUID!) { deleteResourceChart(chartId: $c) }",
        lambda w: {"c": w.pub_chart.id},
    ),
    "publishResourceChart": (
        "mutation ($c: UUID!) { publishResourceChart(chartId: $c) }",
        lambda w: {"c": w.pub_chart.id},
    ),
    "unpublishResourceChart": (
        "mutation ($c: UUID!) { unpublishResourceChart(chartId: $c) }",
        lambda w: {"c": w.pub_chart.id},
    ),
    "createResourceChartImage": (
        f"mutation ($d: UUID!) {{ createResourceChartImage(input: {{dataset: $d}}) {{ {IMAGE} }} }}",
        lambda w: {"d": w.published.id},
    ),
    "addResourceChartImage": (
        f"mutation ($d: UUID!) {{ addResourceChartImage(dataset: $d) {{ {IMAGE} }} }}",
        lambda w: {"d": w.published.id},
    ),
    "updateResourceChartImage": (
        f"""mutation ($i: UUID!, $d: UUID!) {{
          updateResourceChartImage(input: {{id: $i, dataset: $d, name: "x"}}) {{ {IMAGE} }}
        }}""",
        lambda w: {"i": w.pub_image.id, "d": w.published.id},
    ),
    "publishResourceChartImage": (
        "mutation ($i: UUID!) { publishResourceChartImage(resourceChartImageId: $i) }",
        lambda w: {"i": w.pub_image.id},
    ),
    "unpublishResourceChartImage": (
        "mutation ($i: UUID!) { unpublishResourceChartImage(resourceChartImageId: $i) }",
        lambda w: {"i": w.pub_image.id},
    ),
    "deleteResourceChartImage": (
        "mutation ($i: UUID!) { deleteResourceChartImage(resourceChartImageId: $i) }",
        lambda w: {"i": w.pub_image.id},
    ),
    "createAccessModel": (
        f"""mutation ($d: UUID!) {{
          createAccessModel(accessModelInput: {{dataset: $d, name: "x", description: null, type: PUBLIC, resources: []}})
          {{ {AM} }}
        }}""",
        lambda w: {"d": w.published.id},
    ),
    "editAccessModel": (
        f"""mutation ($a: UUID!, $d: UUID!) {{
          editAccessModel(accessModelInput: {{
            accessModelId: $a, dataset: $d, name: "x", description: null, type: null, resources: null
          }}) {{ {AM} }}
        }}""",
        lambda w: {"a": w.pub_am.id, "d": w.published.id},
    ),
    "deleteAccessModel": (
        "mutation ($a: UUID!) { deleteAccessModel(accessModelId: $a) }",
        lambda w: {"a": w.pub_am.id},
    ),
    "updatePromptResource": (
        """mutation ($r: UUID!) {
          updatePromptResource(updateInput: {resource: $r, promptCount: 5}) { success }
        }""",
        lambda w: {"r": w.draft_res.id},
    ),
}


def untouched(w):
    w.pub_chart.refresh_from_db()
    w.pub_image.refresh_from_db()
    w.pub_am.refresh_from_db()
    return (
        w.pub_chart.name == "pc"
        and w.pub_chart.status == "DRAFT"
        and w.pub_image.name == "pi"
        and w.pub_am.name == "pa"
        and ResourceChartDetails.objects.count() == 2
        and ResourceChartImage.objects.count() == 2
        and AccessModel.objects.count() == 2
        and not PromptResource.objects.exists()
    )


@pytest.mark.parametrize("who", ["anonymous", "outsider", "viewer"])
@pytest.mark.parametrize("name", list(MUTATIONS))
def test_people_without_edit_rights_are_refused(world, who, name):
    query, variables = MUTATIONS[name]
    r = run(user_for(world, who), query, **u(variables(world)))
    assert denied(r), (who, name, r.errors, r.data)
    assert untouched(world)


@pytest.mark.parametrize("who", ["owner", "editor", "admin"])
@pytest.mark.parametrize("name", list(MUTATIONS))
def test_people_with_edit_rights_are_let_through(world, who, name):
    query, variables = MUTATIONS[name]
    r = run(world.users[who], query, **u(variables(world)))
    assert not denied(r), (who, name, r.errors, r.data)


@pytest.mark.parametrize(
    "query",
    [
        "mutation ($i: UUID!) { deleteResourceChart(chartId: $i) }",
        "mutation ($i: UUID!) { deleteResourceChartImage(resourceChartImageId: $i) }",
        "mutation ($i: UUID!) { deleteAccessModel(accessModelId: $i) }",
    ],
)
def test_missing_id_is_refused_like_a_forbidden_one(world, query):
    r = run(AnonymousUser(), query, i=str(uuid.uuid4()))
    assert denied(r)
    assert "does not exist" not in str(r.errors)


# Moving something out of a dataset you cannot edit, into one you can.


def test_cannot_move_someone_elses_chart_onto_my_resource(world):
    query, _ = MUTATIONS["editResourceChart"]
    r = run(world.users["outsider"], query, c=str(world.pub_chart.id), r=str(world.their_res.id))
    assert denied(r)
    world.pub_chart.refresh_from_db()
    assert world.pub_chart.resource_id == world.pub_res.id


def test_cannot_move_someone_elses_chart_image_into_my_dataset(world):
    query, _ = MUTATIONS["updateResourceChartImage"]
    r = run(world.users["outsider"], query, i=str(world.pub_image.id), d=str(world.theirs.id))
    assert denied(r)
    world.pub_image.refresh_from_db()
    assert world.pub_image.dataset_id == world.published.id


def test_cannot_take_someone_elses_access_model_by_naming_my_dataset(world):
    query, _ = MUTATIONS["editAccessModel"]
    r = run(world.users["outsider"], query, a=str(world.pub_am.id), d=str(world.theirs.id))
    assert denied(r)


def test_access_model_cannot_include_another_datasets_resource(world):
    r = run(
        world.users["outsider"],
        f"""mutation ($d: UUID!, $r: UUID!) {{
          createAccessModel(accessModelInput: {{
            dataset: $d, name: "x", description: null, type: PUBLIC,
            resources: [{{resource: $r, fields: []}}]
          }}) {{ {AM} }}
        }}""",
        d=str(world.theirs.id),
        r=str(world.draft_res.id),
    )
    assert "does not exist" in str(r.errors or r.data)
    assert not AccessModel.objects.filter(accessmodelresource__resource=world.draft_res).exists()


def test_chart_cannot_use_another_resources_column(world):
    column = ResourceSchema.objects.create(
        resource=world.draft_res, field_name="secret", format="STRING"
    )
    r = run(
        world.users["outsider"],
        f"""mutation ($r: UUID!, $col: String!) {{
          createResourceChart(chartInput: {{resource: $r, options: {{xAxisColumn: $col}}}})
          {{ {CHART} }}
        }}""",
        r=str(world.their_res.id),
        col=str(column.id),
    )
    assert "TypeResourceChart" not in str(r.data) or "does not exist" in str(r.data)
    assert not any(
        "secret" in str(c.options)
        for c in ResourceChartDetails.objects.filter(resource=world.their_res)
    )


# Queries.

LISTS = {
    "chartsDetails": ("query ($d: UUID!) { chartsDetails(datasetId: $d) { id } }", "draft_chart"),
    "datasetResourceCharts": (
        "query ($d: UUID!) { datasetResourceCharts(datasetId: $d) { id } }",
        "draft_image",
    ),
    "accessModelResources": (
        "query ($d: UUID!) { accessModelResources(datasetId: $d) { id } }",
        "draft_am",
    ),
}
ONES = {
    "resourceChart": ("query ($i: UUID!) { resourceChart(chartDetailsId: $i) { id } }", "chart"),
    "resourceChartImage": ("query ($i: UUID!) { resourceChartImage(imageId: $i) { id } }", "image"),
    "accessModel": ("query ($i: UUID!) { accessModel(accessModelId: $i) { id } }", "am"),
}


@pytest.mark.parametrize("name", list(LISTS))
def test_published_lists_stay_public(world, name):
    query, _ = LISTS[name]
    r = run(AnonymousUser(), query, d=str(world.published.id))
    assert r.errors is None and len(r.data[name]) == 1


@pytest.mark.parametrize("name", list(ONES))
def test_published_items_stay_public(world, name):
    query, attr = ONES[name]
    r = run(AnonymousUser(), query, i=str(getattr(world, f"pub_{attr}").id))
    assert r.errors is None and r.data[name]["id"]


@pytest.mark.parametrize("who", ["anonymous", "outsider"])
@pytest.mark.parametrize("name", list(LISTS))
def test_draft_lists_are_hidden(world, who, name):
    query, _ = LISTS[name]
    r = run(user_for(world, who), query, d=str(world.draft.id))
    assert r.errors is None and r.data[name] == []


@pytest.mark.parametrize("who", ["anonymous", "outsider"])
@pytest.mark.parametrize("name", list(ONES))
def test_draft_items_are_hidden(world, who, name):
    query, attr = ONES[name]
    r = run(user_for(world, who), query, i=str(getattr(world, f"draft_{attr}").id))
    assert r.errors and "does not exist" in str(r.errors[0].message)


@pytest.mark.parametrize("who", ["owner", "editor", "viewer", "shared", "admin"])
def test_drafts_visible_to_people_who_can_see_the_draft(world, who):
    user = world.users[who]
    for name, (query, _) in LISTS.items():
        r = run(user, query, d=str(world.draft.id))
        assert r.errors is None and len(r.data[name]) == 1, (who, name, r.errors)
    for name, (query, attr) in ONES.items():
        r = run(user, query, i=str(getattr(world, f"draft_{attr}").id))
        assert r.errors is None, (who, name, r.errors)


def test_all_chart_images_list_hides_drafts(world):
    query = "{ resourceChartImages { name } }"
    r = run(AnonymousUser(), query)
    assert r.errors is None and r.data["resourceChartImages"] == [{"name": "pi"}]
    r = run(world.users["owner"], query)
    assert sorted(i["name"] for i in r.data["resourceChartImages"]) == ["di", "pi"]


def test_all_chart_images_list_still_filters(world):
    r = run(
        world.users["owner"],
        'query { resourceChartImages(filters: {name: "di"}) { name } }',
    )
    assert r.errors is None and r.data["resourceChartImages"] == [{"name": "di"}]
