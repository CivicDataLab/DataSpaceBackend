"""Tests for the migration that adds the "Source identifier" dataset metadata item.

CivicDataLab's scrapers look the item up by its exact label, on datasets, and
only while it is switched on, so these check that the migration leaves exactly
one such item behind, switched on, whatever state it finds.

The test settings skip migrations, so the migration's function is called
directly against the current models.
"""

import importlib

import pytest
from django.apps import apps

from api.models import Metadata

migration = importlib.import_module("api.migrations.0054_add_source_identifier_metadata")


def source_identifier_items():
    return Metadata.objects.filter(label="Source identifier", model="DATASET")


@pytest.mark.django_db
def test_creates_the_item_switched_on_when_missing():
    migration.add_source_identifier(apps, None)

    item = source_identifier_items().get()
    assert item.enabled is True
    assert item.urn == "dataspace-scrapers:source-identifier"
    assert item.data_type == "STRING"
    assert item.type == "OPTIONAL"
    assert item.filterable is False


@pytest.mark.django_db
def test_switches_an_existing_item_back_on_without_adding_another():
    Metadata.objects.create(
        label="Source identifier",
        model="DATASET",
        urn="admin-made:source-identifier",
        data_type="STRING",
        type="OPTIONAL",
        enabled=False,
    )

    migration.add_source_identifier(apps, None)

    item = source_identifier_items().get()
    assert item.enabled is True
    assert item.urn == "admin-made:source-identifier"


@pytest.mark.django_db
def test_running_twice_leaves_one_item():
    migration.add_source_identifier(apps, None)
    migration.add_source_identifier(apps, None)

    assert source_identifier_items().count() == 1


@pytest.mark.django_db
def test_leaves_a_same_named_item_on_another_model_alone():
    resource_item = Metadata.objects.create(
        label="Source identifier",
        model="RESOURCE",
        urn="resource:source-identifier",
        data_type="STRING",
        type="OPTIONAL",
        enabled=False,
    )

    migration.add_source_identifier(apps, None)

    resource_item.refresh_from_db()
    assert resource_item.enabled is False
    assert source_identifier_items().get().urn == "dataspace-scrapers:source-identifier"
