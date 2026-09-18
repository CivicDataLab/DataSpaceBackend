"""Regression test for the same-second slug/title collision.

Root cause: auto-generated titles (e.g. "New dataset 17 Sep 2026 - 09:43:04")
have one-second resolution, and Dataset.slug / UseCase.title+slug /
Collaborative.title+slug are unique columns. Two creates landing in the same
second (routine under concurrent CI load - e.g. `-n 3`) previously raised an
IntegrityError/ValidationError that the create mutation surfaced as a bare
`success: False` with no usable error, which is what made
test_prv_006_org_create_dataset and test_prv_007_org_create_usecase in
CivicDataSpace-test fail under concurrent load (DataSpaceBackend #199).

Model.save() now retries with a disambiguated title/slug on collision
(api/utils/django_utils.py:retry_on_slug_collision), so this same-second
create no longer fails.
"""

import pytest

from api.models import Collaborative, Dataset, UseCase
from authorization.models import User


@pytest.mark.django_db
def test_dataset_same_second_title_does_not_collide():
    same_title = "New dataset 18 Sep 2026 - 09:43:04"
    first = Dataset.objects.create(title=same_title)
    second = Dataset.objects.create(title=same_title)

    assert first.slug != second.slug
    assert second.slug.startswith(first.slug)


@pytest.mark.django_db
def test_usecase_same_second_title_does_not_collide():
    user = User.objects.create(username="collision-user", keycloak_id="collision-user")
    same_title = "New use_case 18 Sep 2026 - 09:43:04"

    first = UseCase.objects.create(title=same_title, user=user)
    second = UseCase.objects.create(title=same_title, user=user)

    assert first.title == same_title
    assert second.title != same_title
    assert second.slug != first.slug


@pytest.mark.django_db
def test_collaborative_same_second_title_does_not_collide():
    user = User.objects.create(username="collision-user-2", keycloak_id="collision-user-2")
    same_title = "New collaborative 18 Sep 2026 - 09:43:04"

    first = Collaborative.objects.create(title=same_title, user=user)
    second = Collaborative.objects.create(title=same_title, user=user)

    assert first.title == same_title
    assert second.title != same_title
    assert second.slug != first.slug
