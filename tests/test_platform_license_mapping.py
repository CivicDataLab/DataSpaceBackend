"""Imported datasets keep the license the platform reported.

SPDX ids map straight onto DatasetLicense; a few platform-specific names go
through LICENSE_ALIASES; anything unknown falls back to CC-BY 4.0.
"""

import csv
import re
from pathlib import Path

import pytest

from api.services.platform_importers.base import map_license
from api.services.platform_importers.github import GitHubImporter
from api.services.platform_importers.huggingface import HuggingFaceImporter
from api.services.platform_importers.kaggle import KaggleImporter

LICENSES_CSV = (
    Path(__file__).resolve().parent.parent / "api/services/metadata_export/contracts/licenses.csv"
)

with open(LICENSES_CSV, encoding="utf-8", newline="") as fh:
    ROWS = list(csv.DictReader(fh))


def _enum_value(row):
    return re.search(r"dataspace_enum=([A-Z0-9_]+)", row["alt_codes"]).group(1)


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r["key"])
def test_spdx_code_maps_to_its_value(row):
    assert map_license(row["code"]) == _enum_value(row)
    assert map_license(row["code"].lower()) == _enum_value(row)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("CC0: Public Domain", "CC0_1_0"),
        ("CC BY-NC-SA 4.0", "CC_BY_NC_SA_4_0"),
        ("Attribution 4.0 International (CC BY 4.0)", "CC_BY_4_0_ATTRIBUTION"),
        ("ODbL", "OPEN_DATABASE_LICENSE"),
        ("GODL-India", "GOVERNMENT_OPEN_DATA_LICENSE"),
        ("MIT", "CC_BY_4_0_ATTRIBUTION"),
        ("", "CC_BY_4_0_ATTRIBUTION"),
    ],
)
def test_platform_names(raw, expected):
    assert map_license(raw) == expected


def test_github_spdx_id():
    assert map_license(GitHubImporter._license({"spdx_id": "CC-BY-NC-4.0"})) == "CC_BY_NC_4_0"
    assert map_license(GitHubImporter._license({"spdx_id": "NOASSERTION"})) == (
        "CC_BY_4_0_ATTRIBUTION"
    )


def test_huggingface_card_and_tag():
    assert map_license(HuggingFaceImporter._license({"license": "cc-by-nc-sa-4.0"}, [])) == (
        "CC_BY_NC_SA_4_0"
    )
    assert map_license(HuggingFaceImporter._license({}, ["license:pddl"])) == "PDDL_1_0"


def test_kaggle_license_name():
    assert map_license(KaggleImporter._license({"licenses": [{"name": "CC0-1.0"}]})) == "CC0_1_0"
    assert map_license(KaggleImporter._license({"licenseName": "ODC-By-1.0"})) == (
        "OPEN_DATA_COMMONS_BY_ATTRIBUTION"
    )
