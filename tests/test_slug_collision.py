"""Regression test for the same-second slug/title collision.

Auto-generated titles (e.g. "New dataset 17 Sep 2026 - 09:43:04") have
one-second resolution, so two creates in the same second get the same title.
Titles and slugs used to be unique, so the second create failed under
concurrent load (DataSpaceBackend #199).

Titles and slugs no longer need to be unique: each record gets its own
public_id, and links are found by that id. Two records may share a title.
"""

import pytest

from api.models import Collaborative, Dataset, Resource, UseCase
from authorization.models import User


@pytest.mark.django_db
def test_dataset_same_second_title_does_not_collide():
    # Dataset slugs are no longer unique; each dataset is found by its own
    # public_id, so two datasets may share a title and slug.
    same_title = "New dataset 18 Sep 2026 - 09:43:04"
    first = Dataset.objects.create(title=same_title)
    second = Dataset.objects.create(title=same_title)

    assert first.slug == second.slug
    assert first.public_id and second.public_id
    assert first.public_id != second.public_id
    assert first.url_slug != second.url_slug


@pytest.mark.django_db
def test_usecase_same_second_title_does_not_collide():
    user = User.objects.create(username="collision-user", keycloak_id="collision-user")
    same_title = "New use_case 18 Sep 2026 - 09:43:04"

    first = UseCase.objects.create(title=same_title, user=user)
    second = UseCase.objects.create(title=same_title, user=user)

    assert first.title == second.title == same_title
    assert first.public_id != second.public_id
    assert first.url_slug != second.url_slug


@pytest.mark.django_db
def test_collaborative_same_second_title_does_not_collide():
    user = User.objects.create(username="collision-user-2", keycloak_id="collision-user-2")
    same_title = "New collaborative 18 Sep 2026 - 09:43:04"

    first = Collaborative.objects.create(title=same_title, user=user)
    second = Collaborative.objects.create(title=same_title, user=user)

    assert first.title == second.title == same_title
    # The slug is also the subdomain, so it stays unique.
    assert first.slug != second.slug
    assert first.public_id != second.public_id
    assert first.url_slug != second.url_slug


@pytest.mark.django_db
def test_resources_with_the_same_name_do_not_collide():
    # Resource slugs are no longer unique (#229): two uploads of the same file
    # name used to race on the unique rule.
    dataset = Dataset.objects.create(title="Resource collision")
    first = Resource.objects.create(dataset=dataset, name="data.csv")
    second = Resource.objects.create(dataset=dataset, name="data.csv")

    assert first.slug == second.slug == "datacsv"
    assert first.pk != second.pk


@pytest.mark.django_db
def test_resource_with_a_preset_slug_keeps_it():
    dataset = Dataset.objects.create(title="Resource preset slug")
    resource = Resource.objects.create(dataset=dataset, name="data.csv", slug="my-file")

    assert resource.slug == "my-file"
