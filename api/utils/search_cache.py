"""Versioned invalidation for cached search results."""

from django.core.cache import cache

SEARCH_CACHE_VERSION_KEY = "search_results_version"


def invalidate_search_cache() -> None:
    """Move cached search results on to a new version.

    Call only after the Elasticsearch write has been refreshed. Search totals are
    read from the index, so bumping any earlier lets a request in the gap cache
    the old results under the new version for the full result TTL.

    The key never expires. Under the cache's default 300s timeout it fell back
    to 0, making results cached under an earlier version 0 reachable again.
    """
    version = cache.get(SEARCH_CACHE_VERSION_KEY, 0)
    cache.set(SEARCH_CACHE_VERSION_KEY, version + 1, timeout=None)
