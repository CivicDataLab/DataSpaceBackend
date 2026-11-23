"""Outbound requests to URLs that users type in (AI model provider endpoints).

The server must never be made to request its own loopback, the private network or
the cloud metadata address on a user's behalf. `resolve_public_url` resolves the
host once and refuses it unless every address is public; callers then connect to
that checked address (`PublicTarget.url`), so a second DNS answer cannot point the
request somewhere else (DNS rebinding). Redirects must stay off for the same reason.
"""

import ipaddress
import socket
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

import httpx

ALLOWED_SCHEMES = ("http", "https")

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


class BlockedURLError(ValueError):
    """The URL is not allowed or its host is not a public address. Message is client-safe."""


class UnresolvedHostError(BlockedURLError):
    """The host has no address (yet). Nothing to connect to, so only calls refuse it."""


NOT_PUBLIC_MESSAGE = "The API endpoint URL must point to a public internet address."
UNRESOLVED_MESSAGE = "The API endpoint URL's host could not be found."
INVALID_MESSAGE = "The API endpoint URL must be a valid http or https URL."


@dataclass(frozen=True)
class PublicTarget:
    """Where to connect: the checked IP, plus what the server expects to see."""

    url: str  # the original URL with its host replaced by the checked IP
    host_header: str  # original host[:port], so virtual hosts still work
    sni_hostname: Optional[str]  # original hostname for TLS (SNI + certificate check)

    def request_kwargs(self) -> Dict:
        extensions = {"sni_hostname": self.sni_hostname} if self.sni_hostname else {}
        return {"headers": {"Host": self.host_header}, "extensions": extensions}


def is_public_address(address: IPAddress) -> bool:
    # IPv4 written as IPv6 (::ffff:127.0.0.1) must be judged as the IPv4 address.
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return not (
        not address.is_global  # loopback, private, link-local (169.254/16), shared, docs
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _parse(url: str) -> httpx.URL:
    # Parse with httpx itself, so the host checked is exactly the one it would connect to.
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, TypeError):
        raise BlockedURLError(INVALID_MESSAGE)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.raw_host:
        raise BlockedURLError(INVALID_MESSAGE)
    return parsed


def _resolve(host: str, port: int) -> List[IPAddress]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise UnresolvedHostError(UNRESOLVED_MESSAGE)
    # Scope ids (fe80::1%eth0) are dropped; such addresses are refused anyway.
    addresses = [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]
    if not addresses:
        raise UnresolvedHostError(UNRESOLVED_MESSAGE)
    return addresses


def resolve_public_url(url: str) -> PublicTarget:
    """Refuse `url` unless it is http(s) and every address its host resolves to is public."""
    parsed = _parse(url)
    host = parsed.raw_host.decode("ascii")  # IDNA-encoded; IPv6 without brackets
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = _resolve(host, port)
    # One private answer is enough to refuse: the client could connect to any of them.
    if not all(is_public_address(address) for address in addresses):
        raise BlockedURLError(NOT_PUBLIC_MESSAGE)

    checked = str(addresses[0])
    try:
        pinned = parsed.copy_with(host=checked)
    except httpx.InvalidURL:
        raise BlockedURLError(INVALID_MESSAGE)
    return PublicTarget(
        url=str(pinned),
        host_header=parsed.netloc.decode("ascii"),  # host[:port], no credentials
        sni_hostname=None if _is_ip(host) else host,
    )


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def public_url_error(url: Optional[str]) -> Optional[str]:
    """Message for a mutation when a non-empty URL is not public, else None.

    A host that does not resolve is accepted: saving must not depend on DNS being up,
    and a call to it is refused anyway."""
    if not url:
        return None
    try:
        resolve_public_url(url)
    except UnresolvedHostError:
        return None
    except BlockedURLError as error:
        return str(error)
    return None
