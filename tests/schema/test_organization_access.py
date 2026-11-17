"""Lists, creation and member lists inside the organisation in the request header.

Root cause: the organisation header only names the organisation the caller is
working in; the context middleware checks that it exists, not that the caller
belongs to it. Use case, collaborative, AI model, publication and event lists
returned the header organisation's items to anyone; `addUseCase`,
`addCollaborative`, `createAiModel`, `createUseCase` and `createCollaborative`
created items for anyone (the last two also took owner, organisation and status
from the input); and `userByOrganization`, `organizationMembers`, `users` and
`searchUsers` listed people without checking who was asking.

Fix: `api/utils/organization_access.py`. Lists and member lists show an
organisation's items only to superusers and members whose role can view
(others get nothing, plus published items with `includePublic`); creating
inside it needs the `add` role there, and the generated create mutations set
id, owner, organisation and draft status on the server
(`api/schema/create_in_organization.py`). `users` is for superusers;
`searchUsers` needs sign-in, matches only a full email and returns no one
else's email.
"""

import types
from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser

from api.models import (
    AIModel,
    Collaborative,
    Event,
    Organization,
    Publication,
    ResourceType,
    UseCase,
)
from api.schema.schema import schema
from api.utils.enums import (
    CollaborativeStatus,
    EventStatus,
    PublicationStatus,
    UseCaseStatus,
)
from authorization.models import OrganizationMembership, Role, User

EMBED = "https://lu.ma/embed/event/evt-abc123/simple"


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
        for n in ["owner", "admin", "editor", "viewer", "outsider", "lone"]
    }
    u["superuser"] = User.objects.create(username="su", keycloak_id="su", is_superuser=True)
    for name, role, o in [
        ("owner", "admin", org),
        ("admin", "admin", org),
        ("editor", "editor", org),
        ("viewer", "viewer", org),
        ("outsider", "admin", other),
    ]:
        OrganizationMembership.objects.create(user=u[name], organization=o, role=roles[role])
    owner = u["owner"]
    rt = ResourceType.objects.create(name="Report")

    def publication(title, status):
        return Publication.objects.create(
            title=title,
            description="d",
            authors=["A"],
            publication_date=date(2024, 1, 1),
            license="CC_BY_4_0_ATTRIBUTION",
            resource_type=rt,
            organization=org,
            user=owner,
            status=status,
        )

    def event(name, status):
        return Event.objects.create(
            name=name,
            location="Pune",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 2),
            luma_embed={"src": EMBED},
            organization=org,
            user=owner,
            status=status,
        )

    def ai_model(name, public):
        return AIModel.objects.create(
            name=name,
            display_name=name,
            description="d",
            model_type="TRANSLATION",
            provider="OPENAI",
            user=owner,
            organization=org,
            is_public=public,
            is_active=True,
        )

    items = {
        "usecase": (
            UseCase.objects.create(
                title="uc draft", user=owner, organization=org, status=UseCaseStatus.DRAFT
            ),
            UseCase.objects.create(
                title="uc pub", user=owner, organization=org, status=UseCaseStatus.PUBLISHED
            ),
        ),
        "collaborative": (
            Collaborative.objects.create(
                title="co draft", user=owner, organization=org, status=CollaborativeStatus.DRAFT
            ),
            Collaborative.objects.create(
                title="co pub", user=owner, organization=org, status=CollaborativeStatus.PUBLISHED
            ),
        ),
        "aimodel": (ai_model("private-model", False), ai_model("public-model", True)),
        "publication": (
            publication("pub draft", PublicationStatus.DRAFT),
            publication("pub pub", PublicationStatus.PUBLISHED),
        ),
        "event": (event("ev draft", EventStatus.DRAFT), event("ev pub", EventStatus.PUBLISHED)),
    }
    return types.SimpleNamespace(u=u, org=org, other=other, items=items)


def user_of(w, who):
    return AnonymousUser() if who == "anon" else w.u[who]


# ---- lists ------------------------------------------------------------------

# (module, query, path to the rows); every query lists the header organisation.
LISTS = [
    ("usecase", "{ useCases { id } }", ["useCases"]),
    ("usecase", "{ useCasesTable { data { id } } }", ["useCasesTable", "data"]),
    ("collaborative", "{ collaboratives { id } }", ["collaboratives"]),
    ("collaborative", "{ collaborativesTable { data { id } } }", ["collaborativesTable", "data"]),
    ("aimodel", "{ aiModels { id } }", ["aiModels"]),
    ("aimodel", "{ aiModelsTable { data { id } } }", ["aiModelsTable", "data"]),
    ("publication", "{ publications { id } }", ["publications"]),
    ("publication", "{ publicationsTable { data { id } } }", ["publicationsTable", "data"]),
    ("event", "{ eventsTable { data { id } } }", ["eventsTable", "data"]),
]


def listed_ids(result, path):
    assert result.errors is None, result.errors
    rows = result.data
    for key in path:
        rows = rows[key]
    return {str(row["id"]) for row in rows}


@pytest.mark.parametrize("module,query,path", LISTS)
@pytest.mark.parametrize("who", ["owner", "admin", "editor", "viewer", "superuser"])
def test_members_list_the_organisation(w, module, query, path, who):
    expected = {str(x.id) for x in w.items[module]}
    assert listed_ids(run(user_of(w, who), query, org=w.org), path) == expected


@pytest.mark.parametrize("module,query,path", LISTS)
@pytest.mark.parametrize("who", ["anon", "outsider", "lone"])
def test_others_get_nothing_for_the_organisation(w, module, query, path, who):
    assert listed_ids(run(user_of(w, who), query, org=w.org), path) == set()


TABLES_WITH_PUBLIC = [
    ("usecase", "{ useCasesTable(includePublic: true) { data { id } } }", "useCasesTable"),
    (
        "collaborative",
        "{ collaborativesTable(includePublic: true) { data { id } } }",
        "collaborativesTable",
    ),
    ("aimodel", "{ aiModelsTable(includePublic: true) { data { id } } }", "aiModelsTable"),
    (
        "publication",
        "{ publicationsTable(includePublic: true) { data { id } } }",
        "publicationsTable",
    ),
]


@pytest.mark.parametrize("module,query,field", TABLES_WITH_PUBLIC)
@pytest.mark.parametrize("who", ["anon", "outsider"])
def test_include_public_adds_only_published_items(w, module, query, field, who):
    published = w.items[module][1]
    got = listed_ids(run(user_of(w, who), query, org=w.org), [field, "data"])
    assert got == {str(published.id)}


def test_no_header_still_lists_own_items(w):
    mine = UseCase.objects.create(title="mine", user=w.u["lone"])
    assert listed_ids(run(w.u["lone"], "{ useCases { id } }"), ["useCases"]) == {str(mine.id)}


def test_charts_table_already_needs_membership(w):
    query = "{ chartsTable { totalItemsCount } }"
    assert run(w.u["outsider"], query, org=w.org).errors
    assert run(AnonymousUser(), query, org=w.org).errors
    member = run(w.u["viewer"], query, org=w.org)
    assert member.errors is None, member.errors


# ---- creating inside the organisation ---------------------------------------

CREATE = {
    "usecase": ("mutation { addUseCase { ... on TypeUseCase { id } } }", UseCase),
    "collaborative": (
        "mutation { addCollaborative { ... on TypeCollaborative { id } } }",
        Collaborative,
    ),
    "aimodel": (
        'mutation { createAiModel(input: {name: "new-model", modelType: TRANSLATION,'
        " provider: OPENAI}) { success } }",
        AIModel,
    ),
}


def created(result, module):
    if module == "aimodel":
        return result.errors is None and result.data["createAiModel"]["success"]
    return result.errors is None and result.data is not None


@pytest.mark.parametrize("module", CREATE)
@pytest.mark.parametrize("who", ["admin", "editor", "superuser"])
def test_members_who_can_add_create_in_the_organisation(w, module, who):
    query, model = CREATE[module]
    before = model.objects.filter(organization=w.org).count()
    assert created(run(w.u[who], query, org=w.org), module)
    assert model.objects.filter(organization=w.org).count() == before + 1


@pytest.mark.parametrize("module", CREATE)
@pytest.mark.parametrize("who", ["viewer", "outsider", "lone", "anon"])
def test_others_cannot_create_in_the_organisation(w, module, who):
    query, model = CREATE[module]
    before = model.objects.count()
    result = run(user_of(w, who), query, org=w.org)
    assert not created(result, module)
    assert model.objects.count() == before


@pytest.mark.parametrize("module", CREATE)
def test_creating_without_a_header_stays_individual(w, module):
    query, model = CREATE[module]
    assert created(run(w.u["lone"], query), module)
    assert model.objects.filter(user=w.u["lone"], organization=None).count() == 1


# ---- the member list --------------------------------------------------------

MEMBERS = "{ userByOrganization { username email } }"


@pytest.mark.parametrize("who", ["admin", "viewer", "superuser"])
def test_members_see_the_member_list(w, who):
    result = run(w.u[who], MEMBERS, org=w.org)
    assert result.errors is None, result.errors
    assert {row["username"] for row in result.data["userByOrganization"]} == {
        "owner",
        "admin",
        "editor",
        "viewer",
    }


@pytest.mark.parametrize("who", ["anon", "outsider", "lone"])
def test_others_get_an_empty_member_list(w, who):
    result = run(user_of(w, who), MEMBERS, org=w.org)
    assert result.errors is None, result.errors
    assert result.data["userByOrganization"] == []


# ---- generated create mutations ---------------------------------------------

# Both inputs list every model field; the server must choose id, public id,
# owner, organisation and status itself.
GENERATED_CREATE = {
    "usecase": ("createUseCase", UseCase, UseCaseStatus.DRAFT),
    "collaborative": ("createCollaborative", Collaborative, CollaborativeStatus.DRAFT),
}


def generated_create(w, module, who, header, row_id=None):
    field, _, _ = GENERATED_CREATE[module]
    query = (
        "mutation($ownerId: ID!, $orgId: ID!, $rowId: ID) {"
        f' {field}(data: {{id: $rowId, title: "made", publicId: "chosen123456",'
        " user: {set: $ownerId}, organization: {set: $orgId}, status: PUBLISHED})"
        " { id status } }"
    )
    return run(
        user_of(w, who),
        query,
        org=header,
        ownerId=str(w.u["owner"].id),
        orgId=str(w.other.id),
        rowId=row_id,
    )


@pytest.mark.parametrize("module", GENERATED_CREATE)
@pytest.mark.parametrize("who", ["admin", "editor", "superuser"])
def test_generated_create_sets_owner_organisation_and_status(w, module, who):
    field, model, draft = GENERATED_CREATE[module]
    result = generated_create(w, module, who, w.org)
    assert result.errors is None, result.errors
    item = model.objects.get(id=result.data[field]["id"])
    assert (item.user, item.organization, item.status) == (w.u[who], w.org, draft)
    assert item.public_id and item.public_id != "chosen123456"


@pytest.mark.parametrize("module", GENERATED_CREATE)
@pytest.mark.parametrize("who", ["viewer", "outsider", "lone", "anon"])
def test_generated_create_refused_for_others(w, module, who):
    _, model, _ = GENERATED_CREATE[module]
    before = model.objects.count()
    assert generated_create(w, module, who, w.org).errors
    assert model.objects.count() == before


@pytest.mark.parametrize("module", GENERATED_CREATE)
def test_generated_create_without_a_header_stays_individual(w, module):
    field, model, draft = GENERATED_CREATE[module]
    result = generated_create(w, module, "lone", None)
    assert result.errors is None, result.errors
    item = model.objects.get(id=result.data[field]["id"])
    assert (item.user, item.organization, item.status) == (w.u["lone"], None, draft)


@pytest.mark.parametrize("module", GENERATED_CREATE)
def test_generated_create_always_makes_a_new_row(w, module):
    field, model, _ = GENERATED_CREATE[module]
    existing = w.items[module][1]
    result = generated_create(w, module, "admin", w.org, row_id=str(existing.id))
    assert result.errors is None, result.errors
    assert str(result.data[field]["id"]) != str(existing.id)
    existing.refresh_from_db()
    assert existing.title != "made"


# ---- other member and user lists --------------------------------------------

ORG_MEMBERS = "query($id: ID!) { organizationMembers(organizationId: $id) { username } }"


@pytest.mark.parametrize("who", ["admin", "viewer", "superuser"])
def test_members_see_organization_members(w, who):
    result = run(w.u[who], ORG_MEMBERS, id=str(w.org.id))
    assert result.errors is None, result.errors
    names = {row["username"] for row in result.data["organizationMembers"]}
    assert names == {"owner", "admin", "editor", "viewer"}


@pytest.mark.parametrize("who", ["anon", "outsider", "lone"])
def test_others_get_no_organization_members(w, who):
    result = run(user_of(w, who), ORG_MEMBERS, id=str(w.org.id))
    assert result.errors is None, result.errors
    assert result.data["organizationMembers"] == []


USERS = "{ users(limit: 50) { username } }"


def test_superusers_list_all_users(w):
    result = run(w.u["superuser"], USERS)
    assert result.errors is None, result.errors
    assert len(result.data["users"]) == len(w.u)


@pytest.mark.parametrize("who", ["anon", "admin", "lone"])
def test_others_get_no_user_list(w, who):
    result = run(user_of(w, who), USERS)
    assert result.errors is None, result.errors
    assert result.data["users"] == []


SEARCH = "query($q: String!) { searchUsers(searchTerm: $q) { username email } }"


def search(w, who, term):
    result = run(user_of(w, who), SEARCH, q=term)
    assert result.errors is None, result.errors
    return {row["username"]: row["email"] for row in result.data["searchUsers"]}


def test_search_users_needs_sign_in(w):
    assert search(w, "anon", "owner") == {}


def test_search_users_by_name_hides_other_emails(w):
    assert search(w, "lone", "owner") == {"owner": ""}
    assert search(w, "lone", "lone") == {"lone": "lone@example.org"}


def test_search_users_matches_only_a_full_email(w):
    assert search(w, "lone", "example.org") == {}
    assert search(w, "lone", "Owner@Example.org") == {"owner": ""}


def test_superusers_see_emails_in_search(w):
    assert search(w, "superuser", "owner") == {"owner": "owner@example.org"}
