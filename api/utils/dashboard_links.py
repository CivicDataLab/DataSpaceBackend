"""Which use case dashboard links may be saved and embedded (#216).

A dashboard link is shown in an iframe on the public use case page, so only
hosts in `settings.DASHBOARD_EMBED_ORIGINS` (or their subdomains) are accepted,
over https on the default port. The backend is the only place this list lives:
the frontend embeds `embedUrl` and asks `checkDashboardLink` while the user types.
"""

import re
from typing import Iterable, Optional
from urllib.parse import urlsplit

from django.conf import settings

from api.models import UseCaseDashboard
from api.utils.input_checks import too_long_error, url_error

NOT_ALLOWED_MESSAGE = "This dashboard link is not allowed."

# Plain DNS names only: percent-encoded or other characters in a host are read
# differently by browsers and by urlsplit.
_HOST = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


class DashboardLinkError(ValueError):
    """A refused link; the message is safe to show to the client."""


def _allowed_hosts() -> list[str]:
    hosts: Iterable[str] = getattr(settings, "DASHBOARD_EMBED_ORIGINS", [])
    return [host.strip().lower().rstrip(".") for host in hosts if host.strip()]


def _host_allowed(host: str) -> bool:
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in _allowed_hosts())


def clean_dashboard_link(link: Optional[str]) -> str:
    """Return the link to store ("" when empty), or raise DashboardLinkError.

    A link without a scheme gets https://, as the frontend does.
    """
    link = (link or "").strip()
    if not link:
        return ""
    # Browsers read a backslash as a slash and drop tabs/newlines, so
    # `https://evil.example\@allowed.host` would embed evil.example.
    if "\\" in link or any(character.isspace() for character in link):
        raise DashboardLinkError(NOT_ALLOWED_MESSAGE)
    if "://" not in link:
        link = f"https://{link}"

    length_message = too_long_error(UseCaseDashboard, "link", link, "Dashboard link")
    if length_message:
        raise DashboardLinkError(length_message)

    parts = urlsplit(link)
    try:
        port = parts.port
    except ValueError:
        raise DashboardLinkError(NOT_ALLOWED_MESSAGE)
    host = (parts.hostname or "").rstrip(".")
    if (
        parts.scheme.lower() != "https"
        or port not in (None, 443)
        or parts.username is not None
        or parts.password is not None
        or not _HOST.match(host)
        or not _host_allowed(host)
        or url_error(link, "Dashboard link", schemes=["https"])
    ):
        raise DashboardLinkError(NOT_ALLOWED_MESSAGE)
    return link


def embed_url(link: Optional[str]) -> Optional[str]:
    """The link to put in the iframe, or None when it may not be embedded."""
    try:
        return clean_dashboard_link(link) or None
    except DashboardLinkError:
        return None
