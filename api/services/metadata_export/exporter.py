"""Orchestrate: model -> record -> crosswalk document -> serialisation fixes -> format.

Which property a value becomes is decided by the contract. What is left here
is serialisation the contract cannot express: typed date literals, IANA
media-type IRIs, and the few structural rules the specs impose on a
Distribution or FileObject.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from api.models import Dataset
from api.services.metadata_export.adapter import IANA_BASE, dataset_to_record
from api.services.metadata_export.crosswalk import Crosswalk
from api.services.metadata_export.formats import allowed_formats, serialise

CROISSANT_CONFORMS_TO = "http://mlcommons.org/croissant/1.1"
XSD_DATE = "http://www.w3.org/2001/XMLSchema#date"
DATE_PROPERTIES = ("dcterms:issued", "dcterms:modified", "dcterms:created")
PERIOD_PROPERTIES = ("dcat:startDate", "dcat:endDate")


def _typed_date(value: Any) -> Any:
    """DCAT-AP expects xsd:date literals; JSON-LD needs the type spelled out."""
    if isinstance(value, str) and len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return {"@value": value[:10], "@type": XSD_DATE}
    return value


def _type_dates(doc: Dict[str, Any]) -> None:
    for prop in DATE_PROPERTIES:
        if prop in doc:
            doc[prop] = _typed_date(doc[prop])
    period = doc.get("dcterms:temporal")
    if isinstance(period, dict):
        for prop in PERIOD_PROPERTIES:
            if prop in period:
                period[prop] = _typed_date(period[prop])


def _by_name(record: Dict[str, Any]) -> Dict[str, dict]:
    return {r.get("name"): r for r in record.get("resources") or [] if r.get("name")}


SPDX_SHA256 = "http://spdx.org/rdf/terms#checksumAlgorithm_sha256"


def _fix_dcat_distributions(doc: Dict[str, Any]) -> None:
    """Media type as an IANA IRI; licence on every distribution; checksum as
    the spdx:Checksum node DCAT-AP prescribes."""
    licence = doc.get("dcterms:license")
    for dist in doc.get("dcat:distribution") or []:
        mt = dist.get("dcat:mediaType")
        if isinstance(mt, str) and "/" in mt:
            dist["dcat:mediaType"] = {"@id": IANA_BASE + mt}
        if licence and "dcterms:license" not in dist:
            dist["dcterms:license"] = licence
        digest = dist.get("spdx:checksum")
        if isinstance(digest, str):
            dist["spdx:checksum"] = {
                "@type": "spdx:Checksum",
                "spdx:algorithm": {"@id": SPDX_SHA256},
                "spdx:checksumValue": digest,
            }


def _fix_croissant_file_objects(doc: Dict[str, Any], record: Dict[str, Any]) -> None:
    """Croissant 1.0 requires @id, contentUrl and encodingFormat on a FileObject.

    Croissant has no accessURL, so for a link-only resource the platform page
    (what a reader can actually fetch) becomes the contentUrl. sha256 is also
    required by the spec and is emitted only when the record carries it.
    """
    resources = _by_name(record)
    landing = record.get("landing_page") or ""
    for n, dist in enumerate(doc.get("distribution") or [], start=1):
        res = resources.get(dist.get("name"), {})
        if "contentUrl" not in dist and res.get("access_url"):
            dist["contentUrl"] = res["access_url"]
        if "encodingFormat" not in dist and res.get("format"):
            dist["encodingFormat"] = res["format"]
        dist.setdefault(
            "@id",
            f"{landing}#resource-{res['_id']}" if res.get("_id") else f"{landing}#resource-{n}",
        )


def _finish(doc: Dict[str, Any], record: Dict[str, Any], standard: str) -> None:
    if standard == "croissant":
        doc.setdefault("conformsTo", CROISSANT_CONFORMS_TO)  # required by the spec
        _fix_croissant_file_objects(doc, record)
    elif standard == "dcat":
        _fix_dcat_distributions(doc)
        _type_dates(doc)
    elif standard == "dublin_core":
        _type_dates(doc)


def export_dataset(
    dataset: Dataset, standard: str, fmt: str = "jsonld"
) -> Tuple[str, str, str, dict]:
    """Return (body, content_type, extension, report)."""
    crosswalk = Crosswalk.load()
    if standard not in crosswalk.standard_ids():
        raise ValueError(
            f"Unknown standard '{standard}'. Known: {', '.join(crosswalk.standard_ids())}"
        )
    if fmt not in allowed_formats(standard):
        raise ValueError(
            f"Format '{fmt}' is not available for {standard}. "
            f"Allowed: {', '.join(allowed_formats(standard))}"
        )

    record = dataset_to_record(dataset)
    doc, report = crosswalk.export_with_report(record, standard)
    doc.setdefault("@id", record["landing_page"])
    _finish(doc, record, standard)
    for definition in record.get("_unmapped_definitions") or []:
        report["dropped"].append(
            {
                "concept": None,
                "dataspace_field": f"metadata:{definition.get('urn') or definition.get('label')}",
                "reason": "definition has no crosswalk concept; give it a recognised URN",
            }
        )

    body, content_type, ext = serialise(doc, fmt)
    return body, content_type, ext, report


def export_options() -> Dict[str, Any]:
    """What the UI can offer: standards, and the formats valid for each."""
    cw = Crosswalk.load()
    return {
        sid: {"name": cw.standard(sid).get("name", sid), "formats": allowed_formats(sid)}
        for sid in cw.standard_ids()
    }
