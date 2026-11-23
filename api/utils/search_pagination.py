"""`page` / `size` for the REST search views, checked before they reach Elasticsearch.

Without this, `size=abc` raised in `int()`, `page=0` or `-1` made a negative slice, and
a page past the first 10 000 hits made Elasticsearch refuse the query: each answered 500
with the raw error text.
"""

from typing import Mapping, Optional, Tuple

# Elasticsearch's default `index.max_result_window`: from + size may not exceed it.
MAX_RESULT_WINDOW = 10_000

NOT_A_NUMBER_MESSAGE = "page and size must be whole numbers of 1 or more."
TOO_DEEP_MESSAGE = (
    f"Only the first {MAX_RESULT_WINDOW} results can be listed. "
    "Use a smaller page or size, or narrow the search."
)


class PaginationError(ValueError):
    """`page` / `size` the search cannot serve. The message is safe to show to clients."""


def _positive_int(raw: Optional[str], default: int) -> int:
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise PaginationError(NOT_A_NUMBER_MESSAGE)
    if value < 1:
        raise PaginationError(NOT_A_NUMBER_MESSAGE)
    return value


def parse_pagination(params: Mapping[str, str], default_size: int = 10) -> Tuple[int, int]:
    """(page, size) from query parameters, or PaginationError."""
    page = _positive_int(params.get("page"), 1)
    size = _positive_int(params.get("size"), default_size)
    if page * size > MAX_RESULT_WINDOW:
        raise PaginationError(TOO_DEEP_MESSAGE)
    return page, size
