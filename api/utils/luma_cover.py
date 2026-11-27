"""
luma_cover
──────────
Look up the cover image of a Luma event from its stored embed URL.

Used while building the event search document, so every index write
(publish, edit, ``search_index --populate`` on deploy) asks Luma afresh; no
value is carried over from a previous index.

- The event id is taken from our own stored embed ``src``
  (``…/embed/event/evt-…``) and must match a strict pattern.
- The request always goes to ``https://api2.luma.com/event/get`` with that id;
  redirects are not followed and at most ``_MAX_BYTES`` are read.
- Only an ``https`` image on ``images.lumacdn.com`` is accepted.

Any failure (no embed, timeout, error status, unexpected body, no image)
returns None and is logged; indexing never fails because of Luma.
"""

import json
import re
from typing import Any, Optional
from urllib.parse import urlparse

import requests
import structlog

logger = structlog.get_logger(__name__)

_EVENT_ID = re.compile(r"^/embed/event/(evt-[A-Za-z0-9]{1,64})(?:/|$)")
_API_URL = "https://api2.luma.com/event/get"
_IMAGE_HOST = "images.lumacdn.com"
_MAX_BYTES = 1_000_000
_TIMEOUT = 3


def luma_event_id(src: Optional[str]) -> Optional[str]:
    """Return the ``evt-…`` id from a Luma event embed URL, or None."""
    if not isinstance(src, str) or not src:
        return None
    match = _EVENT_ID.match(urlparse(src).path)
    return match.group(1) if match else None


def cover_from_response(data: Any, event_id: str) -> Optional[str]:
    """Return ``event.cover_url`` from an ``event/get`` response body, or None."""
    event = data.get("event") if isinstance(data, dict) else None
    if not isinstance(event, dict) or event.get("api_id") != event_id:
        return None
    return _safe_image_url(event.get("cover_url"))


def fetch_luma_cover(embed_src: Optional[str]) -> Optional[str]:
    """Return the cover image URL of the Luma event in ``embed_src``, or None."""
    event_id = luma_event_id(embed_src)
    if not event_id:
        return None
    try:
        with requests.get(
            _API_URL,
            params={"event_api_id": event_id},
            timeout=_TIMEOUT,
            allow_redirects=False,
            stream=True,
            headers={"User-Agent": "DataSpace/1.0", "Accept": "application/json"},
        ) as response:
            if response.status_code != 200:
                logger.warning(
                    "luma_cover_fetch_failed", event_id=event_id, status=response.status_code
                )
                return None
            body = b""
            for chunk in response.iter_content(chunk_size=65536):
                body += chunk
                if len(body) > _MAX_BYTES:
                    logger.warning("luma_cover_response_too_large", event_id=event_id)
                    return None
        cover = cover_from_response(json.loads(body), event_id)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("luma_cover_fetch_failed", event_id=event_id, error=type(exc).__name__)
        return None
    if not cover:
        logger.info("luma_cover_not_found", event_id=event_id)
    return cover


def _safe_image_url(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value or len(value) > 500:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != _IMAGE_HOST:
        return None
    if parsed.username or parsed.password or parsed.port:
        return None
    return value
