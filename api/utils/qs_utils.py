"""Client-driven filtering, sorting and pagination for table-style GraphQL queries.

A client sends ``filters`` as ``[{field, condition, value}]``, ``sort_options``
as ``[{field, direction}]``, plus ``limit`` and ``offset``; the resolver names
which fields may be filtered or sorted. Anything outside that allowlist is a
``ValueError``, which Strawberry surfaces as a GraphQL error.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import strawberry
from django.db.models import Q, QuerySet

MAX_LIMIT = 100

# Generic condition names -> Django lookups. Kept explicit so a client cannot
# reach arbitrary lookups such as ``__regex``.
LOOKUPS = {
    "exact": "exact",
    "iexact": "iexact",
    "contains": "contains",
    "icontains": "icontains",
    "startswith": "startswith",
    "istartswith": "istartswith",
    "endswith": "endswith",
    "iendswith": "iendswith",
    "gt": "gt",
    "gte": "gte",
    "lt": "lt",
    "lte": "lte",
    "in": "in",
    "isnull": "isnull",
}


@strawberry.input(
    description="One filter condition: field, condition (exact, icontains, in, gt …), value."
)
class FilterSpec:
    field: str
    condition: str = "exact"
    value: str = ""


@strawberry.input(description="One sort key: field and direction (asc or desc).")
class SortSpec:
    field: str
    direction: str = "asc"


def _check_allowed(kind: str, field: str, allowed: Optional[Sequence[str]]) -> None:
    if allowed is not None and field not in allowed:
        raise ValueError(
            f"Cannot {kind} on '{field}'. Allowed fields: {', '.join(sorted(allowed))}"
        )


def _coerce(lookup: str, value: str) -> Any:
    if lookup == "in":
        return [v.strip() for v in value.split(",") if v.strip()]
    if lookup == "isnull":
        return value.strip().lower() in ("1", "true", "yes")
    return value


def apply_filters(
    queryset: QuerySet,
    filters: Sequence[FilterSpec],
    allowed_fields: Optional[Sequence[str]] = None,
) -> QuerySet:
    """AND together every condition. Unknown conditions fall back to ``exact``."""
    query = Q()
    for spec in filters or []:
        field = (spec.field or "").strip()
        if not field:
            continue
        _check_allowed("filter", field, allowed_fields)
        lookup = LOOKUPS.get((spec.condition or "exact").strip().lower(), "exact")
        query &= Q(**{f"{field}__{lookup}": _coerce(lookup, spec.value or "")})
    return queryset.filter(query) if query else queryset


def apply_sorting(
    queryset: QuerySet,
    sort_options: Sequence[SortSpec],
    allowed_fields: Optional[Sequence[str]] = None,
) -> QuerySet:
    order: List[str] = []
    for spec in sort_options or []:
        field = (spec.field or "").strip()
        if not field:
            continue
        _check_allowed("sort", field, allowed_fields)
        prefix = "-" if (spec.direction or "asc").strip().lower() == "desc" else ""
        order.append(prefix + field)
    return queryset.order_by(*order) if order else queryset


def apply_pagination(queryset: QuerySet, limit: int, offset: int = 0) -> Dict[str, Any]:
    """Slice one page and return it with the total count and page flags."""
    if limit <= 0 or limit > MAX_LIMIT:
        raise ValueError(f"limit ({limit}) must be between 1 and {MAX_LIMIT}")
    if offset < 0:
        raise ValueError(f"offset ({offset}) must be 0 or more")
    total = queryset.count()
    return {
        "data": queryset[offset : offset + limit],
        "total_items_count": total,
        "has_next": offset + limit < total,
        "has_previous": offset > 0,
    }


def get_pagination_window(
    queryset: QuerySet,
    limit: int,
    offset: int = 0,
    filters: Optional[Sequence[FilterSpec]] = None,
    filtering_allowed_fields: Optional[Sequence[str]] = None,
    sort_options: Optional[Sequence[SortSpec]] = None,
    sorting_allowed_fields: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Filter, then sort, then paginate. Order matters: the count is taken after filtering."""
    if filters:
        queryset = apply_filters(queryset, filters, filtering_allowed_fields)
    if sort_options:
        queryset = apply_sorting(queryset, sort_options, sorting_allowed_fields)
    return apply_pagination(queryset, limit, offset)
