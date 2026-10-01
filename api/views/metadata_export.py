"""GET /api/datasets/<id>/export?standard=dcat|croissant|dublin_core&format=jsonld|turtle|rdfxml|ntriples

Public metadata for a published dataset, generated on request from the
crosswalk contract. Nothing is stored. Add ``report=1`` to receive the gap
report (unresolved vocabulary values, dropped fields, missing mandatory
properties) alongside the document as JSON instead of a file download.
"""

from __future__ import annotations

import json
import uuid

import structlog
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.text import slugify

from api.models import Dataset
from api.services.metadata_export.exporter import export_dataset, export_options
from api.utils.enums import DatasetStatus

logger = structlog.get_logger("dataspace.metadata_export")


def metadata_export_options(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"standards": export_options()})


def metadata_export(request: HttpRequest, dataset_id: uuid.UUID) -> HttpResponse:
    try:
        dataset = Dataset.objects.select_related("organization", "user").get(id=dataset_id)
    except Dataset.DoesNotExist:
        return JsonResponse({"error": "Dataset not found"}, status=404)

    # Public endpoint: published datasets only. Owners preview drafts through
    # the same view when logged in.
    user = getattr(request, "user", None)
    is_owner = bool(
        user and user.is_authenticated and (dataset.user_id == user.id or user.is_superuser)
    )
    if dataset.status != DatasetStatus.PUBLISHED.value and not is_owner:
        return JsonResponse({"error": "Dataset not found"}, status=404)

    standard = (request.GET.get("standard") or "dcat").strip().lower()
    fmt = (request.GET.get("format") or "jsonld").strip().lower()
    try:
        body, content_type, ext, report = export_dataset(dataset, standard, fmt)
    except ValueError as exc:
        return JsonResponse({"error": str(exc), "options": export_options()}, status=400)
    except Exception as exc:  # pragma: no cover - defensive; never 500 on a public page
        logger.error(
            "metadata_export_failed", dataset_id=str(dataset_id), standard=standard, error=str(exc)
        )
        return JsonResponse({"error": "Could not generate the export"}, status=500)

    if request.GET.get("report") in ("1", "true", "yes"):
        payload = {"standard": standard, "format": fmt, "report": report}
        payload["document"] = json.loads(body) if fmt == "jsonld" else body
        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})

    response = HttpResponse(body, content_type=f"{content_type}; charset=utf-8")
    filename = f"{slugify(dataset.slug or dataset.title) or 'dataset'}.{standard}.{ext}"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
