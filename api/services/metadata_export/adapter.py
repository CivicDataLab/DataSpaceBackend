"""Turn a Dataset (and its resources / source) into the flat record the
crosswalk engine reads. This is the only module in the export that knows
Django models; the engine only ever sees plain dicts keyed by the contract's
``dataspace_field`` names. Names that a standard wants as identifiers
(licence, sector, geography, language, access rights) leave here already
resolved to URIs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.conf import settings

from api.models import Dataset, Resource
from api.services import metadata_mapping
from api.services.metadata_export import vocabularies as vocab
from api.utils.enums import DataType

EMPTY = (None, "", [], {})


def _public_base() -> str:
    return getattr(settings, "PUBLIC_SITE_URL", "https://civicdataspace.in").rstrip("/")


def _api_base() -> str:
    return getattr(settings, "PUBLIC_API_URL", "https://api.civicdataspace.in").rstrip("/")


def _iso(dt: Any) -> Optional[str]:
    return dt.date().isoformat() if dt else None


def _is_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


# DCAT-AP mandates the EU Access Right authority list for dcterms:accessRights.
ACCESS_RIGHTS_URI = {
    "PUBLIC": "http://publications.europa.eu/resource/authority/access-right/PUBLIC",
    "RESTRICTED": "http://publications.europa.eu/resource/authority/access-right/RESTRICTED",
    "PRIVATE": "http://publications.europa.eu/resource/authority/access-right/NON_PUBLIC",
}

# Languages are ISO 639-1 codes; the Library of Congress scheme gives each a URI.
LANGUAGE_SCHEME = "http://id.loc.gov/vocabulary/iso639-1/"

# Our format labels -> IANA media types. DCAT-AP wants dcat:mediaType to be an
# IANA IRI and Croissant wants encodingFormat to be a MIME string; both are
# derived from this. Unknown labels pass through lower-cased so nothing is lost.
MEDIA_TYPES = {
    "CSV": "text/csv",
    "TSV": "text/tab-separated-values",
    "TXT": "text/plain",
    "JSON": "application/json",
    "GEOJSON": "application/geo+json",
    "XML": "application/xml",
    "PDF": "application/pdf",
    "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "XLS": "application/vnd.ms-excel",
    "ODS": "application/vnd.oasis.opendocument.spreadsheet",
    "PARQUET": "application/vnd.apache.parquet",
    "ZIP": "application/zip",
    "HTML": "text/html",
}
IANA_BASE = "https://www.iana.org/assignments/media-types/"


def media_type(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    key = str(label).strip().upper().lstrip(".")
    return MEDIA_TYPES.get(key) or (label if "/" in str(label) else str(label).lower())


def _dataset_type_concept(value: Optional[str]) -> Optional[dict]:
    """Our own type vocabulary (DATA / PROMPT), identified under the platform namespace."""
    if not value:
        return None
    return vocab.concept(value, f"{_public_base()}/id/dataset-type/{str(value).lower()}")


def _agent(
    name: Optional[str], uri: Optional[str] = None, kind: str = "foaf:Organization"
) -> Optional[dict]:
    return {"name": name, "uri": uri, "@type": kind} if name else None


def _languages(codes: Any) -> List[dict]:
    out: List[dict] = []
    for code in codes or []:
        code = str(code).strip().lower()
        if code:
            out.append(vocab.concept(code, LANGUAGE_SCHEME + code))
    return out


def resource_to_record(resource: Resource) -> Dict[str, Any]:
    file_details = getattr(resource, "resourcefiledetails", None)
    rec: Dict[str, Any] = {
        "name": resource.name,
        "description": resource.description or None,
        "format": media_type(file_details.format if file_details else None),
        "size": (file_details.size if file_details else None) or None,
        "sha256": (file_details.sha256 if file_details else None) or None,
        "download_url": None,
        "access_url": None,
        "columns": [
            {"name": s.field_name, "type": s.format, "description": s.description or None}
            for s in resource.resourceschema_set.all()
        ],
        "_id": str(resource.id),
        "_kind": "link" if resource.type == DataType.EXTERNAL else "file",
    }
    if resource.type == DataType.EXTERNAL:
        # Link-only: the platform page gives *access*; there is no direct file.
        rec["access_url"] = resource.url or None
        rec["format"] = rec["format"] or "text/html"
    elif file_details and file_details.file:
        rec["download_url"] = f"{_api_base()}/api/download/resource/{resource.id}"
        rec["access_url"] = rec["download_url"]
    return rec


def dataset_to_record(dataset: Dataset) -> Dict[str, Any]:
    source = getattr(dataset, "source", None)
    org = dataset.organization
    user = dataset.user
    landing = f"{_public_base()}/datasets/{dataset.slug}"

    sectors = [vocab.concept(s.name, vocab.sector_uri(s.name)) for s in dataset.sectors.all()]
    geographies = [
        vocab.concept(g.name, vocab.geography_uri(g.name, getattr(g, "type", None)))
        for g in dataset.geographies.all()
    ]
    license_value = dataset.license or None
    license_uri = vocab.license_uri(license_value) or (
        vocab.license_uri(source.source_license) if source and source.source_license else None
    )

    # Who made the data. For an imported dataset that is the platform author,
    # not the person who clicked import; our organisation stays the publisher.
    creator = _agent((user.get_full_name() or user.username) if user else None, kind="foaf:Person")
    if source and source.source_author:
        creator = _agent(source.source_author, kind="foaf:Agent")

    record: Dict[str, Any] = {
        "id": str(dataset.id),
        "slug": dataset.slug,
        "title": dataset.title,
        "description": dataset.description or None,
        "tags": [t.value for t in dataset.tags.all()],
        "sectors": sectors,
        "geographies": geographies,
        "license": license_uri or license_value,
        "organization": _agent(org.name if org else None),
        "user": creator,
        # when the record appeared (here, or on the platform it came from)
        "issued": (
            _iso(source.source_created_at)
            if source and source.source_created_at
            else _iso(dataset.created)
        ),
        "modified": _iso(dataset.modified),
        # when the data itself came into being: only a definition can say
        "created": None,
        "datasetType": _dataset_type_concept(dataset.dataset_type),
        "accessType": vocab.concept(
            dataset.access_type, ACCESS_RIGHTS_URI.get(str(dataset.access_type))
        ),
        "status": dataset.status,
        "resources": [resource_to_record(r) for r in dataset.resources.all()],
        "landing_page": landing,
        "in_catalog": (
            f"{_public_base()}/dataspaces/{dataset.dataspace.slug}"
            if dataset.dataspace_id and getattr(dataset.dataspace, "slug", None)
            else None
        ),
        # provenance and extras, filled for imports; definitions may fill the rest
        "alternative_title": (
            [source.source_identifier] if source and source.source_identifier else []
        ),
        "source": source.source_url if source and source.source_url else None,
        "homepage": source.source_homepage if source and source.source_homepage else None,
        "version": source.revision if source and source.revision else None,
        "citation": source.citation if source and source.citation else None,
        "language": _languages(source.languages) if source and source.languages else [],
    }

    # Definition-backed values (admin-defined fields the publisher filled in),
    # keyed by crosswalk concept. Core columns always win; a definition only
    # supplies what the model has no column for. Unplaceable definitions are
    # carried for the report.
    defined, unmapped = metadata_mapping.definition_values(dataset)
    for concept, value in defined.items():
        if record.get(concept) not in EMPTY:
            continue
        if concept == "language":
            value = _languages(value)
        elif concept in ("source", "homepage") and not _is_url(value):
            continue
        record[concept] = value
    record["_unmapped_definitions"] = unmapped
    return record
