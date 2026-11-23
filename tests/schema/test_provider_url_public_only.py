"""AI model provider endpoints must be public internet addresses.

Root cause: a provider's `apiEndpointUrl` was saved with only a URL-format check,
and `ModelAPIClient` requested it as is, following whatever the host resolved to.
A URL on loopback, the private network or the cloud metadata address made the
server request it and hand the reply (or the raw connection error) to the caller.

Fix: `api/utils/outbound_url.py` resolves the host and refuses it unless every
address is public. Provider create/update check it on save; every call checks it
again and connects to the checked IP only (keeping the hostname for the Host header
and TLS), with redirects off. Failed calls return a fixed message, never raw error
text. No test here uses the network: DNS is stubbed and HTTP is replaced.
"""

import asyncio
import types

import httpx
import pytest
from django.test import RequestFactory

from api.models import AIModel, AIModelVersion, VersionProvider
from api.schema.schema import schema
from api.services.model_api_client import UNREACHABLE_MESSAGE, ModelAPIClient
from api.utils.outbound_url import (
    NOT_PUBLIC_MESSAGE,
    BlockedURLError,
    public_url_error,
    resolve_public_url,
)
from authorization.models import User

PUBLIC_IP = "93.184.215.14"

BLOCKED_URLS = [
    "http://127.0.0.1:8000/health/",  # loopback
    "http://127.1.2.3/",
    "http://0.0.0.0/",  # unspecified
    "http://10.0.0.5/",  # private
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://100.64.0.1/",  # carrier-grade NAT
    "http://169.254.169.254/latest/meta-data/",  # link-local, cloud metadata
    "http://224.0.0.1/",  # multicast
    "http://240.0.0.1/",  # reserved
    "http://[::1]/",  # IPv6 loopback
    "http://[::]/",
    "http://[fc00::1]/",  # IPv6 unique local
    "http://[fe80::1]/",  # IPv6 link-local
    "http://[ff02::1]/",  # IPv6 multicast
    "http://[::ffff:127.0.0.1]/",  # IPv4-mapped IPv6
    "http://[::ffff:169.254.169.254]/",
]


def dns(*addresses):
    """Stand-in for socket.getaddrinfo answering with `addresses`."""

    def getaddrinfo(host, port, *args, **kwargs):
        return [(2, 1, 6, "", (address, port)) for address in addresses]

    return getaddrinfo


@pytest.fixture
def no_dns(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("DNS must not be used for an IP address")

    monkeypatch.setattr("socket.getaddrinfo", fail)


# ─── The address check ────────────────────────────────────────────────────────


@pytest.mark.parametrize("url", BLOCKED_URLS)
def test_internal_addresses_are_refused(no_dns, url):
    with pytest.raises(BlockedURLError, match=NOT_PUBLIC_MESSAGE):
        resolve_public_url(url)


@pytest.mark.parametrize("url", ["http://2130706433/", "http://0x7f000001/", "http://127.1/"])
def test_loopback_in_short_or_numeric_form_is_refused(url):
    # The system resolver reads these as 127.0.0.1 itself; no network is used.
    with pytest.raises(BlockedURLError, match=NOT_PUBLIC_MESSAGE):
        resolve_public_url(url)


@pytest.mark.parametrize("answer", [["10.1.2.3"], ["169.254.169.254"], ["::1"]])
def test_hostname_resolving_to_an_internal_address_is_refused(monkeypatch, answer):
    monkeypatch.setattr("socket.getaddrinfo", dns(*answer))

    with pytest.raises(BlockedURLError, match=NOT_PUBLIC_MESSAGE):
        resolve_public_url("https://models.example.org/v1")


def test_one_internal_answer_among_public_ones_is_refused(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", dns(PUBLIC_IP, "127.0.0.1"))

    with pytest.raises(BlockedURLError):
        resolve_public_url("https://models.example.org/v1")


@pytest.mark.parametrize(
    "url", ["ftp://8.8.8.8/x", "file:///etc/passwd", "gopher://8.8.8.8/", "http:///x"]
)
def test_only_http_and_https_are_allowed(no_dns, url):
    with pytest.raises(BlockedURLError):
        resolve_public_url(url)


def test_public_hostname_connects_to_the_checked_address(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", dns(PUBLIC_IP))

    target = resolve_public_url("https://models.example.org:8443/v1/chat?a=1")

    assert target.url == f"https://{PUBLIC_IP}:8443/v1/chat?a=1"
    assert target.host_header == "models.example.org:8443"
    assert target.sni_hostname == "models.example.org"


def test_public_ip_needs_no_tls_hostname(no_dns):
    target = resolve_public_url("http://8.8.8.8:11434/api/generate")

    assert target.url == "http://8.8.8.8:11434/api/generate"
    assert target.sni_hostname is None


@pytest.fixture
def unknown_host(monkeypatch):
    import socket

    def fail(*args, **kwargs):
        raise socket.gaierror("not found")

    monkeypatch.setattr("socket.getaddrinfo", fail)


def test_unknown_host_is_refused_when_called_but_can_be_saved(unknown_host):
    with pytest.raises(BlockedURLError):
        resolve_public_url("https://no-such-host.example.org/")
    # Nothing to connect to, and saving must not depend on DNS.
    assert public_url_error("https://no-such-host.example.org/") is None


# ─── Saving a provider ────────────────────────────────────────────────────────


def run(user, query, **variables):
    request = RequestFactory().post("/api/graphql")
    request.user = user
    request.context = {}
    ctx = types.SimpleNamespace(request=request, user=user, context={}, response=None)
    return schema.execute_sync(query, variable_values=variables, context_value=ctx)


CREATE = """
mutation($i: CreateVersionProviderInput!) {
  createVersionProvider(input: $i) { success errors { nonFieldErrors } }
}
"""
UPDATE = """
mutation($i: UpdateVersionProviderInput!) {
  updateVersionProvider(input: $i) { success errors { nonFieldErrors } }
}
"""


@pytest.fixture
def owner(db):
    return User.objects.create(username="owner", keycloak_id="owner")


@pytest.fixture
def version(owner):
    model = AIModel.objects.create(
        name="m", display_name="M", model_type="TRANSLATION", provider="CUSTOM", user=owner
    )
    return AIModelVersion.objects.create(ai_model=model, version="1.0")


@pytest.fixture
def provider(version):
    return VersionProvider.objects.create(
        version=version, provider="CUSTOM", api_endpoint_url="https://models.example.org/v1"
    )


def test_create_with_internal_url_is_refused(owner, version, no_dns):
    url = "http://169.254.169.254/latest/meta-data/"
    result = run(
        owner, CREATE, i={"versionId": version.id, "provider": "CUSTOM", "apiEndpointUrl": url}
    )

    payload = result.data["createVersionProvider"]
    assert payload["success"] is False
    assert payload["errors"]["nonFieldErrors"] == [NOT_PUBLIC_MESSAGE]
    assert not VersionProvider.objects.filter(version=version).exists()


def test_update_with_internal_url_is_refused(owner, provider, no_dns):
    result = run(
        owner, UPDATE, i={"id": provider.id, "apiEndpointUrl": "http://127.0.0.1:8000/health/"}
    )

    assert result.data["updateVersionProvider"]["success"] is False
    provider.refresh_from_db()
    assert provider.api_endpoint_url == "https://models.example.org/v1"


def test_public_url_is_saved(owner, version, monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", dns(PUBLIC_IP))
    url = "https://models.example.org/v1"

    result = run(
        owner, CREATE, i={"versionId": version.id, "provider": "CUSTOM", "apiEndpointUrl": url}
    )

    assert result.data["createVersionProvider"]["success"] is True, result
    assert VersionProvider.objects.get(version=version).api_endpoint_url == url


# ─── Calling a provider ───────────────────────────────────────────────────────


class FakeHTTP:
    """Replaces httpx so a call records what it would have sent."""

    def __init__(self, monkeypatch, response=None, error=None):
        self.sent = []
        fake = self

        def request(client, method, url, **kwargs):
            fake.sent.append({"method": method, "url": url, "client": client, **kwargs})
            if error:
                raise error
            return httpx.Response(request=httpx.Request(method, url), **response)

        async def arequest(client, method, url, **kwargs):
            return request(client, method, url, **kwargs)

        monkeypatch.setattr(httpx.Client, "request", request)
        monkeypatch.setattr(httpx.AsyncClient, "request", arequest)


JSON_REPLY = {"status_code": 200, "json": {"text": "hello"}}


def call(provider):
    return ModelAPIClient(provider).call("hi")


def test_stored_internal_url_is_not_requested(provider, no_dns, monkeypatch):
    # Saved before the check existed: the call itself must refuse it.
    VersionProvider.objects.filter(id=provider.id).update(
        api_endpoint_url="http://127.0.0.1:8000/health/"
    )
    provider.refresh_from_db()
    http = FakeHTTP(monkeypatch, response=JSON_REPLY)

    result = call(provider)

    assert result["success"] is False
    assert result["error"] == NOT_PUBLIC_MESSAGE
    assert http.sent == []


def test_host_that_now_resolves_internally_is_not_requested(provider, monkeypatch):
    # The URL was public when saved; its DNS answer changed since.
    monkeypatch.setattr("socket.getaddrinfo", dns("10.0.0.7"))
    http = FakeHTTP(monkeypatch, response=JSON_REPLY)

    assert call(provider)["success"] is False
    assert http.sent == []


def test_call_goes_to_the_checked_address(provider, monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", dns(PUBLIC_IP))
    http = FakeHTTP(monkeypatch, response=JSON_REPLY)

    result = call(provider)

    assert result["success"] is True and result["output"] == "hello"
    [sent] = http.sent
    assert sent["url"] == f"https://{PUBLIC_IP}/v1"
    assert sent["headers"]["Host"] == "models.example.org"
    assert sent["extensions"] == {"sni_hostname": "models.example.org"}
    assert sent["client"].follow_redirects is False


def test_redirect_is_not_followed(provider, monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", dns(PUBLIC_IP))
    redirect = {"status_code": 302, "headers": {"location": "http://169.254.169.254/"}}
    http = FakeHTTP(monkeypatch, response=redirect)

    result = call(provider)

    assert result["success"] is False
    assert result["status_code"] == 302
    assert len(http.sent) == 1


def test_connection_error_text_is_not_returned(provider, monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", dns(PUBLIC_IP))
    FakeHTTP(monkeypatch, error=httpx.ConnectError("[Errno 111] Connection refused"))

    result = call(provider)

    assert result["success"] is False
    assert result["error"] == UNREACHABLE_MESSAGE


def test_provider_error_body_is_not_returned(provider, monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", dns(PUBLIC_IP))
    FakeHTTP(monkeypatch, response={"status_code": 500, "text": "internal detail"})

    result = call(provider)

    assert result["success"] is False
    assert "internal detail" not in result["error"]


def test_async_call_refuses_internal_address(provider, no_dns, monkeypatch):
    VersionProvider.objects.filter(id=provider.id).update(api_endpoint_url="http://[::1]:8000/")
    provider.refresh_from_db()
    http = FakeHTTP(monkeypatch, response=JSON_REPLY)
    client = ModelAPIClient(provider)

    async def no_db():
        return None

    # The bookkeeping save runs in another thread, which the in-memory test DB lacks.
    monkeypatch.setattr(client, "_update_provider_failure", no_db)

    result = asyncio.run(client.call_async("hi"))

    assert result["success"] is False and result["error"] == NOT_PUBLIC_MESSAGE
    assert http.sent == []
