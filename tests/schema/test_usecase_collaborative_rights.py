"""Who may change, delete and see a use case or collaborative.

Root cause: apart from creation, no use case or collaborative mutation had a
permission check, so anyone, even signed out, could edit, link, publish,
unpublish or delete any of them by its sequential id. The use case dashboard
mutations only required sign-in. `useCase(pk)`, `collaborative(pk)`,
`collaborativeBySlug`, the `datasetBy*`/`contributorsBy*` queries and
`usecaseDashboards` returned drafts to anyone.

Fix: `api/utils/owned_item_access.py` holds the rules and the
`Change/Delete{UseCase,Collaborative}Permission` and
`ChangeUseCaseDashboardPermission` classes in `authorization/permissions.py`
apply them to the item named in the arguments (not the organisation header).
Changing (incl. links, publish, unpublish, dashboards) needs the owner, a
superuser, or a member of the item's organisation whose role can change;
deleting needs a role that can delete. Drafts are seen only by the owner,
members whose role can view, and superusers; for anyone else a draft answers
like a missing id.
"""

import re
import types
from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser

from api.models import (
    Collaborative,
    Dataset,
    Organization,
    Publication,
    ResourceType,
    UseCase,
    UseCaseDashboard,
)
from api.schema.schema import schema
from api.utils.enums import CollaborativeStatus, PublicationStatus, UseCaseStatus
from authorization.models import OrganizationMembership, Role, User


def run(user, query, org=None, **variables):
    ctx = types.SimpleNamespace(
        user=user, context={"organization": org} if org else {}, request=None, response=None
    )
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


@pytest.fixture
def w(db):
    roles = {
        "admin": Role.objects.create(
            name="admin", can_view=True, can_add=True, can_change=True, can_delete=True
        ),
        "editor": Role.objects.create(name="editor", can_view=True, can_add=True, can_change=True),
        "viewer": Role.objects.create(name="viewer", can_view=True),
    }
    org = Organization.objects.create(name="Org", description="o", slug="org")
    other = Organization.objects.create(name="Other", description="o", slug="other")
    u = {
        n: User.objects.create(username=n, email=f"{n}@example.org", keycloak_id=n)
        for n in ["creator", "admin", "editor", "viewer", "outsider", "lone"]
    }
    u["superuser"] = User.objects.create(username="su", keycloak_id="su", is_superuser=True)
    u["anonymous"] = AnonymousUser()
    # The creator is only a viewer: owning the item is what lets them change it.
    for name, role, o in [
        ("creator", "viewer", org),
        ("admin", "admin", org),
        ("editor", "editor", org),
        ("viewer", "viewer", org),
        ("outsider", "admin", other),
    ]:
        OrganizationMembership.objects.create(user=u[name], organization=o, role=roles[role])
    creator = u["creator"]
    publication = Publication.objects.create(
        title="p",
        description="d",
        authors=["A"],
        publication_date=date(2024, 1, 1),
        license="CC_BY_4_0_ATTRIBUTION",
        resource_type=ResourceType.objects.create(name="Report"),
        organization=org,
        user=creator,
        status=PublicationStatus.PUBLISHED,
    )
    return types.SimpleNamespace(
        org=org,
        other=other,
        u=u,
        dataset=Dataset.objects.create(title="ds", organization=org, user=creator),
        publication=publication,
        usecase=UseCase.objects.create(
            title="uc", user=creator, organization=org, status=UseCaseStatus.DRAFT
        ),
        collaborative=Collaborative.objects.create(
            title="co", user=creator, organization=org, status=CollaborativeStatus.DRAFT
        ),
        lone_usecase=UseCase.objects.create(
            title="lone uc", user=u["lone"], status=UseCaseStatus.DRAFT
        ),
        lone_collaborative=Collaborative.objects.create(
            title="lone co", user=u["lone"], status=CollaborativeStatus.DRAFT
        ),
    )


UNION = "{ __typename ... on OperationInfo { messages { message } } }"
VAR_TYPES = {
    "id": "String!",
    "uc": "String!",
    "ds": "UUID!",
    "pub": "UUID!",
    "userId": "ID!",
    "orgId": "ID!",
}

# (mutation, arguments, selection) per module; $id is the item under test.
USECASE_MUTATIONS = [
    (
        "addUpdateUsecaseMetadata",
        "updateMetadataInput: {id: $id, metadata: [], tags: null, sectors: []}",
        UNION,
    ),
    ("updateUseCase", 'data: {id: $id, title: "changed"}', "{ id }"),
    ("addDatasetToUseCase", "useCaseId: $id, datasetId: $ds", UNION),
    ("removeDatasetFromUseCase", "useCaseId: $id, datasetId: $ds", UNION),
    ("updateUsecaseDatasets", "useCaseId: $id, datasetIds: [$ds]", UNION),
    ("addPublicationToUseCase", "useCaseId: $id, publicationId: $pub", UNION),
    ("removePublicationFromUseCase", "useCaseId: $id, publicationId: $pub", UNION),
    ("updateUsecasePublications", "useCaseId: $id, publicationIds: [$pub]", UNION),
    ("publishUseCase", "useCaseId: $id", UNION),
    ("unpublishUseCase", "useCaseId: $id", UNION),
    ("addContributorToUseCase", "useCaseId: $id, userId: $userId", UNION),
    ("removeContributorFromUseCase", "useCaseId: $id, userId: $userId", UNION),
    ("updateUsecaseContributors", "useCaseId: $id, userIds: [$userId]", UNION),
    ("addSupportingOrganizationToUseCase", "useCaseId: $id, organizationId: $orgId", UNION),
    ("removeSupportingOrganizationFromUseCase", "useCaseId: $id, organizationId: $orgId", UNION),
    ("addPartnerOrganizationToUseCase", "useCaseId: $id, organizationId: $orgId", UNION),
    ("removePartnerOrganizationFromUseCase", "useCaseId: $id, organizationId: $orgId", UNION),
    (
        "updateUsecaseOrganizationRelationships",
        "useCaseId: $id, supporterOrganizationIds: [$orgId], partnerOrganizationIds: []",
        UNION,
    ),
]
COLLABORATIVE_MUTATIONS = [
    (
        "addUpdateCollaborativeMetadata",
        "updateMetadataInput: {id: $id, metadata: [], tags: null, sectors: [], sdgs: null, "
        "geographies: null}",
        UNION,
    ),
    ("updateCollaborative", 'data: {id: $id, title: "changed"}', "{ id }"),
    ("addDatasetToCollaborative", "collaborativeId: $id, datasetId: $ds", UNION),
    ("removeDatasetFromCollaborative", "collaborativeId: $id, datasetId: $ds", UNION),
    ("updateCollaborativeDatasets", "collaborativeId: $id, datasetIds: [$ds]", UNION),
    ("addUsecaseToCollaborative", "collaborativeId: $id, usecaseId: $uc", UNION),
    ("removeUsecaseFromCollaborative", "collaborativeId: $id, usecaseId: $uc", UNION),
    ("updateCollaborativeUseCases", "collaborativeId: $id, useCaseIds: [$uc]", UNION),
    ("addPublicationToCollaborative", "collaborativeId: $id, publicationId: $pub", UNION),
    ("removePublicationFromCollaborative", "collaborativeId: $id, publicationId: $pub", UNION),
    ("updateCollaborativePublications", "collaborativeId: $id, publicationIds: [$pub]", UNION),
    ("publishCollaborative", "collaborativeId: $id", UNION),
    ("unpublishCollaborative", "collaborativeId: $id", UNION),
    ("addContributorToCollaborative", "collaborativeId: $id, userId: $userId", UNION),
    ("removeContributorFromCollaborative", "collaborativeId: $id, userId: $userId", UNION),
    ("updateCollaborativeContributors", "collaborativeId: $id, userIds: [$userId]", UNION),
    (
        "addSupportingOrganizationToCollaborative",
        "collaborativeId: $id, organizationId: $orgId",
        UNION,
    ),
    (
        "removeSupportingOrganizationFromCollaborative",
        "collaborativeId: $id, organizationId: $orgId",
        UNION,
    ),
    (
        "addPartnerOrganizationToCollaborative",
        "collaborativeId: $id, organizationId: $orgId",
        UNION,
    ),
    (
        "removePartnerOrganizationFromCollaborative",
        "collaborativeId: $id, organizationId: $orgId",
        UNION,
    ),
    (
        "updateCollaborativeOrganizationRelationships",
        "collaborativeId: $id, supporterOrganizationIds: [$orgId], partnerOrganizationIds: []",
        UNION,
    ),
]
MUTATIONS = [("usecase", *m) for m in USECASE_MUTATIONS] + [
    ("collaborative", *m) for m in COLLABORATIVE_MUTATIONS
]
MUTATION_IDS = [m[1] for m in MUTATIONS]

CAN_CHANGE = ["creator", "admin", "editor", "superuser"]
CANNOT_CHANGE = ["viewer", "outsider", "lone", "anonymous"]


def mutate(w, user, name, args, selection, item):
    used = sorted(set(re.findall(r"\$(\w+)", args)))
    defs = ", ".join(f"${v}: {VAR_TYPES[v]}" for v in used)
    values = {
        "id": str(item.id),
        "uc": str(w.usecase.id),
        "ds": str(w.dataset.id),
        "pub": str(w.publication.id),
        "userId": str(w.u["viewer"].id),
        "orgId": str(w.other.id),
    }
    query = f"mutation({defs}) {{ {name}({args}) {selection} }}"
    return run(user, query, **{v: values[v] for v in used})


def messages(result, name):
    found = [e.message for e in result.errors or []]
    payload = (result.data or {}).get(name) or {}
    if isinstance(payload, dict) and payload.get("__typename") == "OperationInfo":
        found += [m["message"] for m in payload["messages"]]
    return found


def refused(result, name):
    return any("permission" in m.lower() for m in messages(result, name))


@pytest.mark.parametrize("module,name,args,selection", MUTATIONS, ids=MUTATION_IDS)
@pytest.mark.parametrize("who", CANNOT_CHANGE)
def test_others_cannot_change(w, module, name, args, selection, who):
    item = getattr(w, module)
    result = mutate(w, w.u[who], name, args, selection, item)
    assert refused(result, name), messages(result, name)
    item.refresh_from_db()
    assert item.title in ("uc", "co") and item.status == "DRAFT"


@pytest.mark.parametrize("module,name,args,selection", MUTATIONS, ids=MUTATION_IDS)
@pytest.mark.parametrize("who", CAN_CHANGE)
def test_owner_superuser_and_changing_roles_are_not_refused(w, module, name, args, selection, who):
    result = mutate(w, w.u[who], name, args, selection, getattr(w, module))
    assert not refused(result, name), messages(result, name)


@pytest.mark.parametrize("module", ["usecase", "collaborative"])
@pytest.mark.parametrize("who", CAN_CHANGE)
def test_update_succeeds_for_those_who_may_change(w, module, who):
    name = "updateUseCase" if module == "usecase" else "updateCollaborative"
    result = mutate(
        w, w.u[who], name, 'data: {id: $id, title: "changed"}', "{ id }", getattr(w, module)
    )
    assert result.errors is None, result.errors
    item = getattr(w, module)
    item.refresh_from_db()
    assert item.title == "changed"


@pytest.mark.parametrize("module", ["usecase", "collaborative"])
@pytest.mark.parametrize("who", ["viewer", "outsider", "anonymous"])
def test_a_missing_id_is_refused_like_a_forbidden_one(w, module, who):
    name = "publishUseCase" if module == "usecase" else "publishCollaborative"
    arg = "useCaseId" if module == "usecase" else "collaborativeId"
    for value in ["999999", "not-a-number"]:
        query = f'mutation {{ {name}({arg}: "{value}") {UNION} }}'
        result = run(w.u[who], query)
        assert refused(result, name), messages(result, name)


# --- delete -----------------------------------------------------------------

DELETES = [
    ("usecase", "deleteUseCase", "useCaseId"),
    ("collaborative", "deleteCollaborative", "collaborativeId"),
]


@pytest.mark.parametrize("module,name,arg", DELETES)
@pytest.mark.parametrize("who", ["creator", "admin", "superuser"])
def test_delete_allowed(w, module, name, arg, who):
    item = getattr(w, module)
    result = run(w.u[who], f"mutation($id: String!) {{ {name}({arg}: $id) }}", id=str(item.id))
    assert result.errors is None, result.errors
    assert not type(item).objects.filter(id=item.id).exists()


@pytest.mark.parametrize("module,name,arg", DELETES)
@pytest.mark.parametrize("who", ["editor", "viewer", "outsider", "lone", "anonymous"])
def test_delete_refused(w, module, name, arg, who):
    item = getattr(w, module)
    result = run(w.u[who], f"mutation($id: String!) {{ {name}({arg}: $id) }}", id=str(item.id))
    assert refused(result, name), messages(result, name)
    assert type(item).objects.filter(id=item.id).exists()


# --- items without an organisation: owner and superusers only ---------------


@pytest.mark.parametrize(
    "module,name",
    [("lone_usecase", "updateUseCase"), ("lone_collaborative", "updateCollaborative")],
)
@pytest.mark.parametrize("who,allowed", [("lone", True), ("superuser", True), ("admin", False)])
def test_individual_items(w, module, name, who, allowed):
    result = mutate(
        w, w.u[who], name, 'data: {id: $id, title: "changed"}', "{ id }", getattr(w, module)
    )
    assert refused(result, name) is not allowed, messages(result, name)


def test_the_organisation_header_does_not_grant_rights(w):
    """An admin of another organisation sending this organisation's header is
    still judged on the item's own organisation."""
    result = run(
        w.u["outsider"],
        'mutation($id: String!) { updateUseCase(data: {id: $id, title: "x"}) { id } }',
        org=w.other,
        id=str(w.usecase.id),
    )
    assert refused(result, "updateUseCase")


# --- dashboards -------------------------------------------------------------

DASHBOARD_SELECTION = "{ success errors { nonFieldErrors } }"


def dashboard_calls(w):
    dashboard = UseCaseDashboard.objects.create(name="d", link="https://x.org", usecase=w.usecase)
    uc = w.usecase.id
    return [
        (
            "addUsecaseDashboards",
            f'input: {{usecaseId: {uc}, dashboards: [{{name: "n", link: "https://y.org"}}]}}',
        ),
        ("addUsecaseDashboard", f'usecaseId: {uc}, name: "n", link: "https://y.org"'),
        ("updateUsecaseDashboard", f'id: "{dashboard.id}", name: "changed"'),
        ("deleteUsecaseDashboard", f"id: {dashboard.id}"),
    ]


@pytest.mark.parametrize("who", ["viewer", "outsider", "lone", "anonymous"])
def test_dashboards_refused_for_others(w, who):
    for name, args in dashboard_calls(w):
        result = run(w.u[who], f"mutation {{ {name}({args}) {DASHBOARD_SELECTION} }}")
        assert result.errors is None, result.errors
        assert result.data[name]["success"] is False, name
    assert UseCaseDashboard.objects.filter(usecase=w.usecase).count() == 1
    assert UseCaseDashboard.objects.get(usecase=w.usecase).name == "d"


@pytest.mark.parametrize("who", CAN_CHANGE)
def test_dashboards_allowed_for_those_who_may_change(w, who):
    for name, args in dashboard_calls(w):
        result = run(w.u[who], f"mutation {{ {name}({args}) {DASHBOARD_SELECTION} }}")
        assert result.errors is None, result.errors
        assert result.data[name]["success"] is True, (name, result.data[name])
    assert not UseCaseDashboard.objects.filter(name="changed").exists()  # updated, then deleted


# --- reads ------------------------------------------------------------------

CAN_SEE_DRAFT = ["creator", "admin", "editor", "viewer", "superuser"]
CANNOT_SEE_DRAFT = ["outsider", "lone", "anonymous"]


def reads(w, module, item):
    """Each single-item read for the module, returning (query, check(result) -> seen)."""
    if module == "usecase":
        return [
            (f"{{ useCase(pk: {item.id}) {{ id }} }}", lambda r: r.data is not None),
            (
                f'{{ contributorsByUseCase(useCaseId: "{item.id}") {{ id }} }}',
                lambda r: r.data is not None,
            ),
            (
                f'{{ datasetByUseCase(useCaseId: "{item.id}") {{ id }} }}',
                lambda r: bool(r.data and r.data["datasetByUseCase"]),
            ),
            (
                f"{{ usecaseDashboards(usecaseId: {item.id}) {{ id }} }}",
                lambda r: r.data is not None,
            ),
            (
                "{ usecaseDashboardsAll(filters: {}, order: {}, "
                "pagination: {offset: 0, limit: 10}) { id } }",
                lambda r: bool(r.data and r.data["usecaseDashboardsAll"]),
            ),
        ]
    return [
        (f"{{ collaborative(pk: {item.id}) {{ id }} }}", lambda r: r.data is not None),
        (
            f'{{ collaborativeBySlug(publicId: "{item.public_id}") {{ id }} }}',
            lambda r: r.data is not None,
        ),
        (
            f'{{ contributorsByCollaborative(collaborativeId: "{item.id}") {{ id }} }}',
            lambda r: r.data is not None,
        ),
        (
            f'{{ datasetByCollaborative(collaborativeId: "{item.id}") {{ id }} }}',
            lambda r: bool(r.data and r.data["datasetByCollaborative"]),
        ),
    ]


@pytest.fixture
def linked(w):
    for item in (w.usecase, w.collaborative):
        item.datasets.add(w.dataset)
    UseCaseDashboard.objects.create(name="d", link="https://x.org", usecase=w.usecase)
    return w


@pytest.mark.parametrize("module", ["usecase", "collaborative"])
@pytest.mark.parametrize("who", CAN_SEE_DRAFT)
def test_drafts_seen_by_owner_members_and_superusers(linked, module, who):
    for query, seen in reads(linked, module, getattr(linked, module)):
        result = run(linked.u[who], query)
        assert seen(result), (query, result.errors)


@pytest.mark.parametrize("module", ["usecase", "collaborative"])
@pytest.mark.parametrize("who", CANNOT_SEE_DRAFT)
def test_drafts_hidden_from_others(linked, module, who):
    for query, seen in reads(linked, module, getattr(linked, module)):
        result = run(linked.u[who], query)
        assert not seen(result), query


@pytest.mark.parametrize("module", ["usecase", "collaborative"])
@pytest.mark.parametrize("who", CANNOT_SEE_DRAFT)
def test_published_items_seen_by_everyone(linked, module, who):
    item = getattr(linked, module)
    item.status = "PUBLISHED"
    item.save()
    for query, seen in reads(linked, module, item):
        result = run(linked.u[who], query)
        assert seen(result), (query, result.errors)


@pytest.mark.parametrize(
    "query",
    [
        "{{ useCase(pk: {uc}) {{ id }} }}",
        "{{ collaborative(pk: {co}) {{ id }} }}",
    ],
)
def test_a_hidden_draft_answers_like_a_missing_id(w, query):
    hidden = run(AnonymousUser(), query.format(uc=w.usecase.id, co=w.collaborative.id))
    missing = run(AnonymousUser(), query.format(uc=999999, co=999999))
    assert [e.message for e in hidden.errors] == [e.message for e in missing.errors]
    assert hidden.errors[0].message.endswith("matching query does not exist.")
