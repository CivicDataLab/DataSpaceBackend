"""Patch for OpenTelemetry Elasticsearch instrumentation to handle list bodies."""

import functools
from typing import Any, Dict, List, Optional, Union

from opentelemetry.instrumentation.elasticsearch.utils import (
    sanitize_body as original_sanitize_body,
)


def patched_sanitize_body(
    body: Optional[Union[Dict[str, Any], List[Any], str]]
) -> Optional[str]:
    """Patched version of sanitize_body that handles list bodies properly.

    Args:
        body: The request body to sanitize

    Returns:
        A sanitized string representation of the body
    """
    if body is None:
        return None

    # Handle list case (for bulk operations)
    if isinstance(body, list):
        # For bulk operations, just return a simplified representation
        return f"[... {len(body)} bulk operations ...]"

    # Use the original function for dictionaries and strings
    result: Optional[str] = original_sanitize_body(body)
    return result  # Explicitly typed as Optional[str]


def patch_elasticsearch_instrumentation() -> None:
    """Apply the patch to the Elasticsearch instrumentation."""
    # Import here to avoid circular imports
    from opentelemetry.instrumentation.elasticsearch import utils
    from opentelemetry.instrumentation.elasticsearch.utils import sanitize_body

    # Replace the original function with our patched version
    utils.sanitize_body = patched_sanitize_body
