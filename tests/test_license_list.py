"""DatasetLicense offers one choice per row of contracts/licenses.csv.

The CSV is the source of truth: its ``dataspace_enum`` alt code names the enum
value, its label is the choice label, and its URI is what the metadata export
emits for that value.
"""

import csv
import re
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from api.models import Dataset, Publication
from api.schema.schema import schema
from api.services.metadata_export import vocabularies as vocab
from api.services.metadata_export.exporter import export_dataset
from api.services.publication_service import validate_draft_inputs
from api.utils.enums import DatasetLicense
from tests.schema.test_publication_schema import (  # noqa: F401  (fixtures)
    CREATE,
    _no_activity_recording,
    ctx,
    geography,
    org_a,
    org_a_admin,
    resource_type,
    roles,
    run,
    sector,
    valid_create_vars,
)

LICENSES_CSV = (
    Path(__file__).resolve().parent.parent / "api/services/metadata_export/contracts/licenses.csv"
)


def _rows():
    with open(LICENSES_CSV, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


ROWS = _rows()


def _enum_value(row):
    match = re.search(r"dataspace_enum=([A-Z0-9_]+)", row["alt_codes"])
    assert match, f"{row['key']} has no dataspace_enum alt code"
    return match.group(1)


class TestEnumMatchesCsv:
    def test_one_choice_per_row(self):
        assert sorted(DatasetLicense.values) == sorted(_enum_value(r) for r in ROWS)

    def test_labels_come_from_the_csv(self):
        labels = dict(DatasetLicense.choices)
        for row in ROWS:
            assert labels[_enum_value(row)] == " ".join(row["label"].split()), row["key"]

    def test_existing_values_are_unchanged(self):
        # Stored rows use these; renaming one would orphan data.
        for value in (
            "GOVERNMENT_OPEN_DATA_LICENSE",
            "CC_BY_4_0_ATTRIBUTION",
            "CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE",
            "OPEN_DATA_COMMONS_BY_ATTRIBUTION",
            "OPEN_DATABASE_LICENSE",
        ):
            assert value in DatasetLicense.values

    def test_values_fit_the_column(self):
        field = Dataset._meta.get_field("license")
        assert max(len(v) for v in DatasetLicense.values) <= field.max_length

    @pytest.mark.parametrize("row", ROWS, ids=lambda r: r["key"])
    def test_every_value_resolves_to_its_uri(self, row):
        assert vocab.license_uri(_enum_value(row)) == row["uri"]


@pytest.mark.django_db
class TestStorageAndExport:
    @pytest.mark.parametrize("value", ["CC_BY_NC_ND_4_0", "CC0_1_0", "CC_BY_4_0_ATTRIBUTION"])
    def test_dataset_exports_the_license_uri(self, value, org_a):  # noqa: F811
        dataset = Dataset.objects.create(title="Rainfall", organization=org_a, license=value)
        body, _, _, _ = export_dataset(dataset, "dcat", "jsonld")
        assert vocab.license_uri(value) in body

    def test_value_outside_the_list_is_rejected(self, org_a):  # noqa: F811
        dataset = Dataset(title="Rainfall", organization=org_a, license="MIT")
        with pytest.raises(ValidationError) as exc:
            dataset.full_clean(exclude=["slug", "user", "dataspace", "description"])
        assert "license" in exc.value.message_dict


class TestGraphQL:
    def test_enum_exposes_every_value(self):
        result = schema.execute_sync('{ __type(name: "DatasetLicense") { enumValues { name } } }')
        assert result.errors is None
        names = {v["name"] for v in result.data["__type"]["enumValues"]}
        assert names == set(DatasetLicense.values)

    @pytest.mark.django_db
    @pytest.mark.parametrize("value", ["CC_BY_NC_4_0", "PDDL_1_0"])
    def test_create_publication_accepts_new_values(
        self, value, org_a_admin, org_a, resource_type, sector, geography  # noqa: F811
    ):
        result = run(
            CREATE,
            ctx(org_a_admin, org_a),
            valid_create_vars(resource_type, sector, geography, license=value),
        )
        assert result.errors is None
        payload = result.data["createPublication"]
        assert payload["success"] is True
        assert Publication.objects.get(id=payload["data"]["id"]).license == value

    def test_service_validation_uses_the_full_list(self):
        validate_draft_inputs(license_value="CC_BY_SA_3_0_IGO")
        with pytest.raises(ValidationError):
            validate_draft_inputs(license_value="NOT_A_LICENSE")
