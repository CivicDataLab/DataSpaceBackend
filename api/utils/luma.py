"""
luma
────
Parse a pasted Luma iframe into a small set of attributes.

The stored value is not the raw HTML. ``src`` must be an ``https`` embed on
``lu.ma`` or ``luma.com``. Width, height, and the other presentation
attributes Luma includes are kept. Event handlers, ``srcdoc``, and any tag
other than one iframe are rejected.
"""

import re
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urlparse, urlunparse

from django.core.exceptions import ValidationError

_LUMA_HOSTS = {"lu.ma", "www.lu.ma", "luma.com", "www.luma.com"}
_SIZE = re.compile(r"^\d{1,4}(px|%)?$")
_ALLOW = re.compile(r"^[A-Za-z0-9; _-]+$")
_UNSAFE_STYLE = re.compile(
    r"javascript:|expression\s*\(|url\s*\(|@import|behavior\s*:|[<>\"']",
    re.IGNORECASE,
)
_REFERRERS = {
    "no-referrer",
    "no-referrer-when-downgrade",
    "origin",
    "origin-when-cross-origin",
    "same-origin",
    "strict-origin",
    "strict-origin-when-cross-origin",
    "unsafe-url",
}
_LOADING = {"eager", "lazy"}


class _IframeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.attrs: Optional[dict[str, str]] = None
        self.iframe_count = 0
        self.other_tags = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        name = tag.lower()
        if name == "iframe":
            self.iframe_count += 1
            if self.iframe_count == 1:
                self.attrs = {key.lower(): value or "" for key, value in attrs}
            return
        self.other_tags = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        self.handle_starttag(tag, attrs)


def canonical_luma_src(value: Optional[str]) -> Optional[str]:
    """Return a canonical Luma embed URL, or None."""
    if not value or not value.strip():
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme != "https":
        return None
    if parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").lower()
    if host not in _LUMA_HOSTS:
        return None
    if not parsed.path.startswith("/embed/"):
        return None
    return urlunparse(("https", host, parsed.path, "", parsed.query, ""))


def parse_luma_embed(value: Optional[str]) -> Optional[dict[str, object]]:
    """Return whitelisted iframe attributes, or None when the paste is not a Luma embed."""
    if not value or not value.strip():
        return None

    trimmed = value.strip()
    parser = _IframeParser()
    parser.feed(trimmed)
    parser.close()
    if parser.other_tags or parser.iframe_count > 1:
        return None
    if parser.iframe_count == 1 and parser.attrs is not None:
        return _attributes(parser.attrs)
    if parser.iframe_count == 0:
        src = canonical_luma_src(trimmed)
        return {"src": src} if src else None
    return None


def validate_luma_embed(value: Optional[str]) -> dict[str, object]:
    """Return the whitelisted attributes, or raise ValidationError."""
    embed = parse_luma_embed(value)
    if not embed:
        raise ValidationError("Enter a valid Luma embed URL or iframe.")
    return embed


def extract_luma_embed_url(value: Optional[str]) -> Optional[str]:
    """Return only the embed URL. Kept for callers that do not need the other attributes."""
    embed = parse_luma_embed(value)
    if not embed:
        return None
    src = embed.get("src")
    return src if isinstance(src, str) else None


def _attributes(attrs: dict[str, str]) -> Optional[dict[str, object]]:
    if any(name.startswith("on") or name in {"srcdoc", "formaction"} for name in attrs):
        return None
    src = canonical_luma_src(attrs.get("src"))
    if not src:
        return None

    embed: dict[str, object] = {"src": src}
    width = _size(attrs.get("width"))
    height = _size(attrs.get("height"))
    style = _style(attrs.get("style"))
    title = _plain(attrs.get("title"), 200)
    allow = _allow(attrs.get("allow"))
    frameborder = _size(attrs.get("frameborder"))
    referrer = (attrs.get("referrerpolicy") or "").strip().lower()
    loading = (attrs.get("loading") or "").strip().lower()

    if width:
        embed["width"] = width
    if height:
        embed["height"] = height
    if style:
        embed["style"] = style
    if title:
        embed["title"] = title
    if allow:
        embed["allow"] = allow
    if "allowfullscreen" in attrs:
        embed["allowfullscreen"] = True
    if frameborder:
        embed["frameborder"] = frameborder
    if referrer in _REFERRERS:
        embed["referrerpolicy"] = referrer
    if loading in _LOADING:
        embed["loading"] = loading
    return embed


def _size(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    if _SIZE.match(cleaned):
        return cleaned
    return None


def _style(value: Optional[str]) -> Optional[str]:
    cleaned = " ".join((value or "").split())
    if not cleaned or len(cleaned) > 500 or _UNSAFE_STYLE.search(cleaned):
        return None
    return cleaned


def _plain(value: Optional[str], limit: int) -> Optional[str]:
    cleaned = " ".join((value or "").split())
    if not cleaned or "<" in cleaned or ">" in cleaned:
        return None
    return cleaned[:limit]


def _allow(value: Optional[str]) -> Optional[str]:
    cleaned = " ".join((value or "").split())
    if not cleaned or len(cleaned) > 200 or not _ALLOW.match(cleaned):
        return None
    return cleaned
