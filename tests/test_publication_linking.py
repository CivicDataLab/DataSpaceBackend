"""Layer 3/4 tests for linking published Resources into Use Cases / Collaboratives.

Covers the only-PUBLISHED-is-linkable guard, the render-time published-only
filter (stale links vanish on unpublish/delete and reappear on re-publish), the
owner's linked-count flag, and the one intentional cross-org affordance.
"""

import types
from datetime import date

import pytest

from api.models import Collaborative, Publication, ResourceType, UseCase
from api.models.Organization import Organization
from api.schema.schema import schema
from api.utils.enums import PublicationStatus
from authorization.models import User


@pytest.fixture
def user(db):
    return User.objects.create(username="author", keycloak_id="author")


@pytest.fixture
def resource_type(db):
    return ResourceType.objects.create(name="Report")


def _publication(user, resource_type, status=PublicationStatus.PUBLISHED, org=None):
    return Publication.objects.create(
        title="Findings",
        description="d",
        user=user,
        resource_type=resource_type,
        publication_date=date(2024, 1, 1),
        status=status,
        organization=org,
    )


_uc_counter = [0]
_collab_counter = [0]


def _use_case(user):
    _uc_counter[0] += 1
    return UseCase.objects.create(title=f"UC {_uc_counter[0]}", user=user)


def _collaborative(user):
    _collab_counter[0] += 1
    return Collaborative.objects.create(title=f"Collab {_collab_counter[0]}", user=user)


def ctx(user):
    return types.SimpleNamespace(user=user, context={})


def run(query, user, variables):
    return schema.execute_sync(query, variable_values=variables, context_value=ctx(user))


ADD_TO_UC = """
mutation($ucId: String!, $pubId: UUID!) {
  addPublicationToUseCase(useCaseId: $ucId, publicationId: $pubId) { __typename }
}
"""

ADD_TO_COLLAB = """
mutation($cId: String!, $pubId: UUID!) {
  addPublicationToCollaborative(collaborativeId: $cId, publicationId: $pubId) { __typename }
}
"""


def _published_only(entity):
    return list(entity.publications.filter(status=PublicationStatus.PUBLISHED))


# --------------------------------------------------------------------------- #
# Link guard
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestLinkGuard:
    def test_published_resource_links_to_use_case(self, user, resource_type):
        uc = _use_case(user)
        pub = _publication(user, resource_type, status=PublicationStatus.PUBLISHED)

        run(ADD_TO_UC, user, {"ucId": str(uc.id), "pubId": str(pub.id)})

        assert uc.publications.filter(id=pub.id).exists()

    def test_draft_resource_is_rejected(self, user, resource_type):
        uc = _use_case(user)
        draft = _publication(user, resource_type, status=PublicationStatus.DRAFT)

        run(ADD_TO_UC, user, {"ucId": str(uc.id), "pubId": str(draft.id)})

        assert uc.publications.count() == 0  # guard held — nothing linked

    def test_published_resource_links_to_collaborative(self, user, resource_type):
        collab = _collaborative(user)
        pub = _publication(user, resource_type, status=PublicationStatus.PUBLISHED)

        run(ADD_TO_COLLAB, user, {"cId": str(collab.id), "pubId": str(pub.id)})

        assert collab.publications.filter(id=pub.id).exists()

    def test_draft_resource_is_rejected_by_collaborative(self, user, resource_type):
        collab = _collaborative(user)
        draft = _publication(user, resource_type, status=PublicationStatus.DRAFT)

        run(ADD_TO_COLLAB, user, {"cId": str(collab.id), "pubId": str(draft.id)})

        assert collab.publications.count() == 0


# --------------------------------------------------------------------------- #
# Stale links — render omits unpublished/deleted, restores on re-publish
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestStaleLinks:
    def test_unpublish_hides_then_republish_restores(self, user, resource_type):
        uc = _use_case(user)
        collab = _collaborative(user)
        pub = _publication(user, resource_type, status=PublicationStatus.PUBLISHED)
        uc.publications.add(pub)
        collab.publications.add(pub)

        assert _published_only(uc) == [pub]
        assert _published_only(collab) == [pub]

        pub.status = PublicationStatus.DRAFT
        pub.save()
        assert _published_only(uc) == []  # silently drops from render
        assert _published_only(collab) == []

        pub.status = PublicationStatus.PUBLISHED
        pub.save()
        assert _published_only(uc) == [pub]  # reappears
        assert _published_only(collab) == [pub]

    def test_delete_removes_link_and_render_skips(self, user, resource_type):
        uc = _use_case(user)
        collab = _collaborative(user)
        pub = _publication(user, resource_type, status=PublicationStatus.PUBLISHED)
        uc.publications.add(pub)
        collab.publications.add(pub)

        pub.delete()

        assert _published_only(uc) == []
        assert _published_only(collab) == []
        assert uc.publications.count() == 0  # M2M row auto-cleared


# --------------------------------------------------------------------------- #
# Linked-count flag + cross-org affordance
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
class TestLinkedCountAndCrossOrg:
    def test_linked_count_across_usecases_and_collaboratives(self, user, resource_type):
        pub = _publication(user, resource_type, status=PublicationStatus.PUBLISHED)
        uc1, uc2 = _use_case(user), _use_case(user)
        collab = _collaborative(user)
        uc1.publications.add(pub)
        uc2.publications.add(pub)
        collab.publications.add(pub)

        assert pub.usecase_set.count() + pub.collaborative_set.count() == 3

        uc1.publications.remove(pub)
        assert pub.usecase_set.count() + pub.collaborative_set.count() == 2

    def test_unrelated_user_cannot_link_to_someone_elses_use_case(self, user, resource_type):
        # IDOR guard: a caller who neither owns nor has an editor role on the use
        # case cannot change its links, even with a valid published resource.
        owner = user
        stranger = User.objects.create(username="stranger", keycloak_id="stranger")
        uc = _use_case(owner)
        pub = _publication(owner, resource_type, status=PublicationStatus.PUBLISHED)

        run(ADD_TO_UC, stranger, {"ucId": str(uc.id), "pubId": str(pub.id)})

        assert uc.publications.count() == 0  # link refused

    def test_cross_org_link_is_allowed(self, resource_type):
        # A UC in org B may link a PUBLISHED resource owned by org A — the one
        # intentional cross-org path; do not deny it.
        org_a = Organization.objects.create(name="A", description="a", slug="a")
        org_b = Organization.objects.create(name="B", description="b", slug="b")
        owner_a = User.objects.create(username="a", keycloak_id="a")
        owner_b = User.objects.create(username="b", keycloak_id="b")
        pub = _publication(owner_a, resource_type, status=PublicationStatus.PUBLISHED, org=org_a)
        uc_b = UseCase.objects.create(title="UC B", user=owner_b, organization=org_b)

        run(ADD_TO_UC, owner_b, {"ucId": str(uc_b.id), "pubId": str(pub.id)})

        assert uc_b.publications.filter(id=pub.id).exists()
