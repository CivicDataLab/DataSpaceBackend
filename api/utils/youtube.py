"""
youtube
───────
Parse and validate YouTube links for content blocks.

``extract_video_id`` pulls the 11-character video id out of any of the common
YouTube URL shapes (``watch?v=``, ``youtu.be/``, ``embed/``); ``validate_youtube_url``
is the boundary guard — it returns that id or raises a clean ValidationError for
anything that isn't a recognisable YouTube video link.
"""

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError

# A YouTube video id is exactly 11 url-safe characters.
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


def extract_video_id(url: Optional[str]) -> Optional[str]:
    """Return the 11-char video id from a YouTube url, or None if it isn't one.

    Handles ``watch?v=<id>``, the ``youtu.be/<id>`` short link, and the
    ``/embed/<id>`` player link. Any other host or a malformed id yields None.
    """
    if not url or not url.strip():
        return None

    parsed = urlparse(url.strip())
    # Reject anything that isn't a plain http(s) link — a matching host on a
    # ``javascript:`` scheme (e.g. ``javascript://youtube.com/watch?v=...``)
    # must never pass, or it becomes a stored-XSS vector when rendered.
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return None

    candidate: Optional[str] = None
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        values = parse_qs(parsed.query).get("v")
        candidate = values[0] if values else None
    elif parsed.path.startswith(("/embed/", "/v/", "/shorts/")):
        candidate = parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else None

    if candidate and _VIDEO_ID.match(candidate):
        return candidate
    return None


def validate_youtube_url(url: Optional[str]) -> str:
    """Return the video id for a valid YouTube url, else raise ValidationError."""
    video_id = extract_video_id(url)
    if not video_id:
        raise ValidationError("Enter a valid YouTube video URL.")
    return video_id
