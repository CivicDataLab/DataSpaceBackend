"""Patch for OpenTelemetry Elasticsearch instrumentation to handle list bodies."""

from typing import Any, Dict, List, Optional, Union, cast


def patched_flatten_dict(d: Union[Dict[str, Any], List[Any], str]) -> Dict[str, Any]:
    """Patched version of _flatten_dict that handles lists properly.

    Args:
        d: The object to flatten, can be a dict, list, or string

    Returns:
        A flattened dictionary
    """
    result: Dict[str, Any] = {}

    # Handle list case (for bulk operations)
    if isinstance(d, list):
        result["bulk_operations"] = f"[{len(d)} operations]"
        return result

    # Handle string case
    if isinstance(d, str):
        result["body"] = d
        return result

    # Handle dict case (original behavior)
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, dict):
                for k2, v2 in patched_flatten_dict(v).items():
                    result[f"{k}.{k2}"] = v2
            elif isinstance(v, list):
                result[k] = f"[list of {len(v)} items]"
            else:
                result[k] = v

    return result


def patch_elasticsearch_instrumentation() -> None:
    """Apply the patch to the Elasticsearch instrumentation.

    This patches the internal _flatten_dict function which is causing the error.
    """
    # Import here to avoid circular imports
    from opentelemetry.instrumentation.elasticsearch import utils

    # Replace the internal _flatten_dict function with our patched version
    utils._flatten_dict = patched_flatten_dict  # type: ignore
