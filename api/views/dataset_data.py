"""HTTP endpoints for fetching indexed dataset/resource data from data_db.

Endpoints:

- ``GET /api/resources/<resource_id>/data/`` — fetch indexed data for a single
  resource with column-based filtering.
- ``GET /api/datasets/<dataset_id>/data/`` — fetch indexed data for a dataset.
  By default operates on the dataset's first indexed resource. Pass
  ``?resource_id=<uuid>`` to target a specific resource.
- ``GET /api/datasets/<dataset_id>/prompts/`` — fetch indexed data for a
  PromptDataset, restricted to ``dataset_type=PROMPT`` and exposing extra
  prompt-specific filter shorthands.

All endpoints accept these query params:

- ``columns`` — comma-separated list of columns to project.
- ``limit`` (default 100, max 10000), ``offset`` (default 0).
- ``order_by`` — comma-separated columns; prefix with ``-`` for DESC.
- ``count`` — ``true``/``false`` (default ``true``) to include total row count.
- Any other query param is interpreted as a data-column filter, optionally
  with operator suffix, e.g. ``?price__gte=10&category=books``. Repeated keys
  produce a list (used naturally for ``__in``/``__nin``).
"""

import uuid
from typing import Any, Dict, List, Optional, Tuple

import structlog
from django.http import HttpRequest
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Dataset, Resource, ResourceDataTable
from api.models.PromptDataset import PromptDataset
from api.utils.data_indexing import (
    DEFAULT_FETCH_LIMIT,
    MAX_FETCH_LIMIT,
    DataFetchError,
    fetch_resource_data,
    get_resource_columns,
)
from api.utils.enums import DatasetStatus, DatasetType

logger = structlog.get_logger(__name__)

# Reserved query parameters that are NOT treated as column filters.
_RESERVED_PARAMS = {
    "columns",
    "limit",
    "offset",
    "order_by",
    "count",
    "resource_id",
    "format",
}


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_csv(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


def _extract_filters(query_params: Any, reserved: Optional[set] = None) -> Dict[str, Any]:
    """Pull non-reserved query params as filter dict.

    Repeated keys collapse into lists so callers can use
    ``?col__in=a&col__in=b``. ``__in``/``__nin`` always produce a list, even
    for a single value.
    """
    reserved_set = reserved if reserved is not None else _RESERVED_PARAMS
    filters: Dict[str, Any] = {}
    # query_params is a QueryDict; use .lists() if available
    if hasattr(query_params, "lists"):
        items = query_params.lists()
    else:
        items = [(k, [v]) for k, v in query_params.items()]

    for key, values in items:
        if key in reserved_set:
            continue
        if not values:
            continue
        op_suffix = key.rsplit("__", 1)[-1] if "__" in key else None
        if op_suffix in ("in", "nin"):
            # Allow comma-separated single value too
            collected: List[Any] = []
            for v in values:
                if isinstance(v, str) and "," in v:
                    collected.extend([p for p in (s.strip() for s in v.split(",")) if p])
                else:
                    collected.append(v)
            filters[key] = collected
        else:
            # Last value wins for non-list operators
            filters[key] = values[-1]
    return filters


def _user_can_access_dataset(request: HttpRequest, dataset: Dataset) -> bool:
    """Allow access to PUBLISHED datasets, otherwise require owner/org-member."""
    if dataset.status == DatasetStatus.PUBLISHED.value:
        return True
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if dataset.user_id and dataset.user_id == user.id:
        return True
    if dataset.organization_id:
        # Lazy import to avoid circular imports at module load
        from authorization.models import OrganizationMembership

        return OrganizationMembership.objects.filter(
            user=user, organization_id=dataset.organization_id
        ).exists()
    return False


def _resolve_dataset_resource(
    dataset: Dataset, resource_id: Optional[str]
) -> Tuple[Optional[Resource], Optional[Response]]:
    """Pick a Resource for a dataset-level data fetch.

    Returns ``(resource, error_response)`` — exactly one is non-None.
    """
    if resource_id:
        try:
            resource = dataset.resources.get(id=resource_id)
        except Resource.DoesNotExist:
            return None, Response(
                {"error": f"Resource {resource_id} not found in dataset {dataset.id}"},
                status=404,
            )
        return resource, None

    # Default: first resource that has indexed data
    indexed_table = (
        ResourceDataTable.objects.filter(resource__dataset=dataset).order_by("created").first()
    )
    if indexed_table is None:
        return None, Response(
            {
                "error": (
                    "Dataset has no indexed (tabular) resources. "
                    "Pass ?resource_id=<uuid> or upload a CSV/XLSX/Parquet/JSON file."
                )
            },
            status=404,
        )
    return indexed_table.resource, None


def _fetch_and_respond(
    request: Request,
    resource: Resource,
    extra_filters: Optional[Dict[str, Any]] = None,
    reserved: Optional[set] = None,
    extra_response: Optional[Dict[str, Any]] = None,
) -> Response:
    """Common path: parse query params, run fetch_resource_data, return JSON."""
    qp = request.query_params  # type: ignore[attr-defined]

    columns = _parse_csv(qp.get("columns"))
    order_by = _parse_csv(qp.get("order_by"))
    limit = _parse_int(qp.get("limit"), DEFAULT_FETCH_LIMIT)
    offset = _parse_int(qp.get("offset"), 0)
    count = _parse_bool(qp.get("count"), default=True)

    filters = _extract_filters(qp, reserved=reserved)
    if extra_filters:
        filters.update(extra_filters)

    try:
        result = fetch_resource_data(
            resource=resource,
            filters=filters,
            columns=columns,
            limit=limit,
            offset=offset,
            order_by=order_by,
            count=count,
        )
    except DataFetchError as e:
        return Response({"error": str(e)}, status=400)
    except Exception as e:  # pragma: no cover — defensive
        logger.exception(
            "fetch_resource_data failed",
            resource_id=str(resource.id),
            error=str(e),
        )
        return Response({"error": "Failed to fetch data"}, status=500)

    available = get_resource_columns(resource)

    payload: Dict[str, Any] = {
        "resource_id": str(resource.id),
        "dataset_id": str(resource.dataset_id),
        "available_columns": available,
        "max_limit": MAX_FETCH_LIMIT,
        **result,
    }
    if extra_response:
        payload.update(extra_response)
    return Response(payload)


class ResourceDataView(APIView):
    """Return indexed data for a specific resource."""

    permission_classes = [AllowAny]

    def get(self, request: Request, resource_id: uuid.UUID) -> Response:
        try:
            resource = Resource.objects.select_related("dataset").get(id=resource_id)
        except Resource.DoesNotExist:
            return Response({"error": "Resource not found"}, status=404)

        if not _user_can_access_dataset(request, resource.dataset):  # type: ignore[attr-defined]
            return Response({"error": "Not authorized"}, status=403)

        return _fetch_and_respond(request, resource)


class DatasetDataView(APIView):
    """Return indexed data for a dataset (one resource at a time)."""

    permission_classes = [AllowAny]

    def get(self, request: Request, dataset_id: uuid.UUID) -> Response:
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            return Response({"error": "Dataset not found"}, status=404)

        if not _user_can_access_dataset(request, dataset):
            return Response({"error": "Not authorized"}, status=403)

        resource_id = request.query_params.get("resource_id")  # type: ignore[attr-defined]
        resource, err = _resolve_dataset_resource(dataset, resource_id)
        if err is not None:
            return err
        assert resource is not None
        return _fetch_and_respond(request, resource)


class PromptDatasetDataView(APIView):
    """Return indexed data for a PromptDataset.

    Same query semantics as :class:`DatasetDataView`, but the dataset must be
    of type ``PROMPT``. Convenience query params (translated to column
    filters when those columns exist on the data):

    - ``prompt_contains`` -> ``prompt__icontains``
    - ``response_contains`` -> ``response__icontains`` (or ``completion``)
    - ``min_length``/``max_length`` -> ``length__gte``/``length__lte``
    """

    permission_classes = [AllowAny]

    # Conventional column names we look for on prompt data tables.
    _PROMPT_COL_CANDIDATES = ("prompt", "input", "instruction", "question")
    _RESPONSE_COL_CANDIDATES = ("response", "completion", "answer", "output")
    _LENGTH_COL_CANDIDATES = ("length", "prompt_length", "tokens", "token_count")

    def _first_present(self, available: List[str], candidates: Tuple[str, ...]) -> Optional[str]:
        lower_map = {c.lower(): c for c in available}
        for cand in candidates:
            if cand in lower_map:
                return lower_map[cand]
        return None

    def get(self, request: Request, dataset_id: uuid.UUID) -> Response:
        try:
            prompt_dataset = PromptDataset.objects.get(dataset_ptr_id=dataset_id)
        except PromptDataset.DoesNotExist:
            return Response(
                {"error": f"Dataset {dataset_id} is not a prompt dataset"},
                status=404,
            )

        if prompt_dataset.dataset_type != DatasetType.PROMPT.value:
            return Response(
                {"error": f"Dataset {dataset_id} is not a prompt dataset"},
                status=400,
            )

        if not _user_can_access_dataset(request, prompt_dataset):
            return Response({"error": "Not authorized"}, status=403)

        resource_id = request.query_params.get("resource_id")  # type: ignore[attr-defined]
        resource, err = _resolve_dataset_resource(prompt_dataset, resource_id)
        if err is not None:
            return err
        assert resource is not None

        # Map prompt-specific shorthands to underlying column filters
        available = get_resource_columns(resource)
        qp = request.query_params  # type: ignore[attr-defined]
        extra: Dict[str, Any] = {}

        prompt_col = self._first_present(available, self._PROMPT_COL_CANDIDATES)
        response_col = self._first_present(available, self._RESPONSE_COL_CANDIDATES)
        length_col = self._first_present(available, self._LENGTH_COL_CANDIDATES)

        prompt_q = qp.get("prompt_contains")
        if prompt_q and prompt_col:
            extra[f"{prompt_col}__icontains"] = prompt_q

        response_q = qp.get("response_contains")
        if response_q and response_col:
            extra[f"{response_col}__icontains"] = response_q

        min_len = qp.get("min_length")
        if min_len and length_col:
            extra[f"{length_col}__gte"] = min_len

        max_len = qp.get("max_length")
        if max_len and length_col:
            extra[f"{length_col}__lte"] = max_len

        local_reserved = _RESERVED_PARAMS | {
            "prompt_contains",
            "response_contains",
            "min_length",
            "max_length",
        }

        return _fetch_and_respond(
            request,
            resource,
            extra_filters=extra,
            reserved=local_reserved,
            extra_response={
                "dataset_type": prompt_dataset.dataset_type,
                "prompt_column": prompt_col,
                "response_column": response_col,
                "length_column": length_col,
            },
        )
