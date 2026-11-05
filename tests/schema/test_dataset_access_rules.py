"""One dataset edit rule, any-grant view rule, organisation listings for
members only, and refused changes are logged."""

import types
import uuid

import pytest
from django.contrib.auth.models import AnonymousUser

from api.models import Dataset, Organization, Resource
from api.schema.dataset_schema import UpdateDatasetPermission
from api.schema.schema import schema
from api.utils.dataset_access import (
    can_change_dataset,
    can_view_dataset,
    viewable_datasets_q,
)
from authorization.models import DatasetPermission, OrganizationMembership, Role, User


def ctx(user, org=None):
    return types.SimpleNamespace(
        user=user,
        context={"organization": org, "auth_token": "CANARY-TOKEN"} if org else {},
        request=None,
        response=None,
    )


def info(user):
    return types.SimpleNamespace(context=ctx(user), field_name="updateDataset")


def run(user, query, org=None, **variables):
    return schema.execute_sync(query, variable_values=variables, context_value=ctx(user, org))


@pytest.fixture
def w(db):
    roles = {
        "admin": Role.objects.create(
            name="admin", can_view=True, can_add=True, can_change=True, can_delete=True
        ),
        "editor": Role.objects.create(name="editor", can_view=True, can_add=True, can_change=True),
        "viewer": Role.objects.create(name="viewer", can_view=True),
        "manager": Role.objects.create(
            name="manager", can_view=True, can_change=True, can_delete=True
        ),
        "ds_editor": Role.objects.create(name="dataset-editor", can_view=True, can_change=True),
        "blind": Role.objects.create(name="blind", can_view=False),
    }
    org = Organization.objects.create(name="Org", description="o", slug="org")
    other = Organization.objects.create(name="Other", description="o", slug="other")
    names = [
        "owner",
        "admin",
        "editor",
        "viewer",
        "manager",
        "other_admin",
        "stranger",
        "dp_change",
        "dp_elsewhere",
        "viewer_blind_dp",
        "solo",
    ]
    u = {
        n: User.objects.create(username=f"u-{n}-name", email=f"{n}@example.org", keycloak_id=n)
        for n in names
    }
    u["superuser"] = User.objects.create(username="su", keycloak_id="su", is_superuser=True)
    for n, r, o in [
        ("admin", "admin", org),
        ("editor", "editor", org),
        ("viewer", "viewer", org),
        ("manager", "manager", org),
        ("viewer_blind_dp", "viewer", org),
        ("other_admin", "admin", other),
    ]:
        OrganizationMembership.objects.create(user=u[n], organization=o, role=roles[r])

    def ds(slug, status="DRAFT", **kw):
        return Dataset.objects.create(title=slug, slug=slug, description="d", status=status, **kw)

    d = types.SimpleNamespace(
        draft=ds("draft", user=u["owner"], organization=org),
        published=ds("pub", "PUBLISHED", user=u["owner"], organization=org),
        archived=ds("arch", "ARCHIVED", user=u["owner"], organization=org),
        solo=ds("solo", user=u["solo"]),
    )
    for x in (d.draft, d.published, d.archived):
        DatasetPermission.objects.create(user=u["dp_change"], dataset=x, role=roles["ds_editor"])
    DatasetPermission.objects.create(
        user=u["dp_elsewhere"], dataset=d.solo, role=roles["ds_editor"]
    )
    DatasetPermission.objects.create(
        user=u["viewer_blind_dp"], dataset=d.draft, role=roles["blind"]
    )
    return types.SimpleNamespace(u=u, d=d, org=org, other=other)


# ---- the edit rule ---------------------------------------------------------

EDIT = {
    # user: (draft, published, archived)
    "owner": (True, True, True),
    "admin": (True, True, True),
    "editor": (True, True, True),
    "viewer": (False, False, False),
    "manager": (False, False, False),  # org edit rights follow the role name
    "other_admin": (False, False, False),
    "stranger": (False, False, False),
    "dp_change": (True, False, False),
    "dp_elsewhere": (False, False, False),
    "superuser": (True, True, True),
}


@pytest.mark.parametrize("who", EDIT)
def test_edit_rule(w, who):
    got = tuple(can_change_dataset(w.u[who], x) for x in (w.d.draft, w.d.published, w.d.archived))
    assert got == EDIT[who]


@pytest.mark.parametrize("who", EDIT)
def test_update_dataset_permission_uses_edit_rule(w, who):
    perm = UpdateDatasetPermission()
    for x, expected in zip((w.d.draft, w.d.published, w.d.archived), EDIT[who]):
        for key in ("update_dataset_input", "update_metadata_input", "update_input"):
            got = perm.has_permission(
                None, info(w.u[who]), **{key: types.SimpleNamespace(dataset=x.id)}
            )
            assert bool(got) == expected, (who, x.status, key)


def test_update_dataset_permission_edges(w):
    perm = UpdateDatasetPermission()
    editor, su = w.u["editor"], w.u["superuser"]
    unknown = types.SimpleNamespace(dataset=uuid.uuid4())
    assert not perm.has_permission(None, info(AnonymousUser()), update_input=unknown)
    assert not perm.has_permission(None, info(editor))
    assert not perm.has_permission(None, info(editor), update_input=types.SimpleNamespace())
    assert not perm.has_permission(None, info(editor), update_input=unknown)
    # Superusers still pass before the lookup, as before.
    assert perm.has_permission(None, info(su))
    assert perm.has_permission(None, info(su), update_input=unknown)


def test_null_owner_and_org_dataset(w):
    orphan = Dataset.objects.create(title="o", slug="orphan", description="d")
    DatasetPermission.objects.create(
        user=w.u["dp_change"], dataset=orphan, role=Role.objects.get(name="dataset-editor")
    )
    assert not can_change_dataset(w.u["editor"], orphan)
    assert not can_view_dataset(w.u["stranger"], orphan)
    assert can_change_dataset(w.u["dp_change"], orphan)
    assert can_change_dataset(w.u["superuser"], orphan)


# ---- the view rule ---------------------------------------------------------

VIEW_DRAFT = {
    "owner": True,
    "admin": True,
    "editor": True,
    "viewer": True,
    "manager": True,
    "other_admin": False,
    "stranger": False,
    "dp_change": True,
    "dp_elsewhere": False,
    "viewer_blind_dp": True,  # any one grant is enough
    "superuser": True,
}


@pytest.mark.parametrize("who", VIEW_DRAFT)
def test_view_rule_matches_list_filter(w, who):
    user = w.u[who]
    for x in (w.d.draft, w.d.archived):
        expected = VIEW_DRAFT[who]
        assert can_view_dataset(user, x) == expected, (who, x.status)
        listed = Dataset.objects.filter(viewable_datasets_q(user), id=x.id).exists()
        assert listed == expected, (who, x.status)
    assert can_view_dataset(user, w.d.published)


def test_anonymous_view_no_queries(w, django_assert_num_queries):
    with django_assert_num_queries(0):
        assert can_view_dataset(AnonymousUser(), w.d.published)
        assert not can_view_dataset(AnonymousUser(), w.d.draft)
        assert not can_change_dataset(AnonymousUser(), w.d.draft)


# ---- the organisation header ----------------------------------------------

DATASETS = "query ($p: Boolean) { datasets(includePublic: $p) { id } }"
TABLE = "query { datasetsTable(limit: 50) { data { id } totalItemsCount } }"
NESTED = "query { datasets { resources { id name } } }"


def ids(r, field="datasets"):
    assert r.errors is None, r.errors
    rows = r.data[field]["data"] if field == "datasetsTable" else r.data[field]
    return {row["id"] for row in rows}


@pytest.mark.parametrize("who", ["anon", "stranger", "other_admin"])
def test_header_does_not_list_another_orgs_drafts(w, who):
    user = AnonymousUser() if who == "anon" else w.u[who]
    Resource.objects.create(name="secret.csv", dataset=w.d.draft)
    assert ids(run(user, DATASETS, org=w.org)) == set()
    assert ids(run(user, TABLE, org=w.org), "datasetsTable") == set()
    r = run(user, NESTED, org=w.org)
    assert "secret.csv" not in str(r.data) and r.errors is None
    # includePublic still adds published datasets, and only those.
    assert ids(run(user, DATASETS, org=w.org, p=True)) == {str(w.d.published.id)}


@pytest.mark.parametrize("who", ["viewer", "editor", "admin", "superuser"])
def test_members_list_their_orgs_datasets(w, who):
    expected = {str(x.id) for x in (w.d.draft, w.d.published, w.d.archived)}
    assert ids(run(w.u[who], DATASETS, org=w.org)) == expected
    assert ids(run(w.u[who], TABLE, org=w.org), "datasetsTable") == expected


def test_no_header_lists_own_solo_datasets(w):
    assert ids(run(w.u["solo"], DATASETS)) == {str(w.d.solo.id)}


# ---- refusals are logged ---------------------------------------------------

RENAME = """mutation ($id: UUID!) {
  updateFileResource(fileResourceInput: {id: $id, name: "x"}) { ... on TypeResource { name } }
}"""


def denial_records(caplog):
    out = []
    for rec in caplog.records:
        msg = rec.msg if isinstance(rec.msg, dict) else {}
        if msg.get("event") == "dataset access denied":
            out.append(msg)
    return out


@pytest.mark.parametrize(
    "who,reason",
    [("anon", "not_signed_in"), ("other_admin", "not_allowed"), ("unknown", "target_not_found")],
)
def test_refusal_logged_once_without_personal_data(w, caplog, who, reason):
    res = Resource.objects.create(name="f.csv", dataset=w.d.draft)
    user = AnonymousUser() if who == "anon" else w.u["other_admin"]
    rid = uuid.uuid4() if who == "unknown" else res.id
    caplog.set_level("WARNING")
    r = run(user, RENAME, org=w.org, id=str(rid))
    assert r.errors
    res.refresh_from_db()
    assert res.name == "f.csv"
    recs = denial_records(caplog)
    assert len(recs) == 1
    assert recs[0]["reason"] == reason
    assert recs[0]["operation"] == "updateFileResource"
    assert recs[0]["user_id"] == getattr(user, "id", None)
    for rec in caplog.records:
        text = rec.getMessage() + str(rec.msg)
        for secret in ("CANARY-TOKEN", "other_admin@example.org", "u-other_admin-name"):
            assert secret not in text


def test_allowed_change_logs_nothing(w, caplog):
    res = Resource.objects.create(name="f.csv", dataset=w.d.draft)
    caplog.set_level("WARNING")
    r = run(w.u["editor"], RENAME, org=w.org, id=str(res.id))
    assert r.errors is None, r.errors
    assert denial_records(caplog) == []


def test_old_resource_permission_class_removed():
    import authorization.permissions as p

    assert not hasattr(p, "ResourcePermissionGraphQL")
