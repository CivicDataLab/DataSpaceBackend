"""Luma cover image on the event search document."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from api.models import Event
from api.utils.enums import EventStatus
from api.utils.luma_cover import cover_from_response, fetch_luma_cover, luma_event_id
from search.documents import EventDocument

EMBED = "https://lu.ma/embed/event/evt-abc123/simple"
COVER = "https://images.lumacdn.com/gallery-images/rc/5f979993.png"
NEW_COVER = "https://images.lumacdn.com/gallery-images/7t/2758125c.png"


def body(event: object) -> dict:
    return {"api_id": "x", "event": event}


def response(status: int = 200, payload: object = None, raw: bytes = b"") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.iter_content.return_value = [raw or json.dumps(payload).encode()]
    resp.__enter__.return_value = resp
    return resp


# ── embed id ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "src, expected",
    [
        (EMBED, "evt-abc123"),
        ("https://luma.com/embed/event/evt-abc123", "evt-abc123"),
        ("https://luma.com/embed/calendar/cal-x/events", None),
        ("https://luma.com/embed/event/../../admin/simple", None),
        ("", None),
        (None, None),
        (123, None),
    ],
)
def test_event_id_comes_only_from_an_event_embed(src, expected):
    assert luma_event_id(src) == expected


# ── response parsing ─────────────────────────────────────────────────────


def test_cover_is_read_from_the_event():
    assert (
        cover_from_response(body({"api_id": "evt-abc123", "cover_url": COVER}), "evt-abc123")
        == COVER
    )


def test_cover_of_another_event_is_ignored():
    assert (
        cover_from_response(body({"api_id": "evt-zzz", "cover_url": COVER}), "evt-abc123") is None
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://images.lumacdn.com/x.png",
        "https://evil.example.com/x.png",
        "https://images.lumacdn.com.evil.example/x.png",
        "https://user@images.lumacdn.com/x.png",
        "",
        None,
        123,
    ],
)
def test_only_https_luma_cdn_images_are_accepted(url):
    assert (
        cover_from_response(body({"api_id": "evt-abc123", "cover_url": url}), "evt-abc123") is None
    )


@pytest.mark.parametrize("data", [{}, [], "x", None, body(None), body("x")])
def test_unexpected_body_gives_no_cover(data):
    assert cover_from_response(data, "evt-abc123") is None


# ── fetching ─────────────────────────────────────────────────────────────


@patch("api.utils.luma_cover.requests.get")
def test_fetch_calls_event_get_with_the_id_without_redirects(get):
    get.return_value = response(payload=body({"api_id": "evt-abc123", "cover_url": COVER}))
    assert fetch_luma_cover(EMBED) == COVER
    assert get.call_args.args[0] == "https://api2.luma.com/event/get"
    assert get.call_args.kwargs["params"] == {"event_api_id": "evt-abc123"}
    assert get.call_args.kwargs["allow_redirects"] is False
    assert get.call_args.kwargs["timeout"] <= 5


@pytest.mark.parametrize(
    "resp",
    [
        requests.Timeout(),
        requests.ConnectionError(),
        response(status=404, payload={"message": "not found"}),
        response(status=302, payload={}),
        response(status=500, payload={}),
        response(raw=b"<html>not json</html>"),
    ],
)
@patch("api.utils.luma_cover.requests.get")
def test_fetch_failures_give_null(get, resp):
    if isinstance(resp, Exception):
        get.side_effect = resp
    else:
        get.return_value = resp
    assert fetch_luma_cover(EMBED) is None


@patch("api.utils.luma_cover._MAX_BYTES", 10)
@patch("api.utils.luma_cover.requests.get")
def test_oversized_response_is_not_read(get):
    get.return_value = response(payload=body({"api_id": "evt-abc123", "cover_url": COVER}))
    assert fetch_luma_cover(EMBED) is None


@patch("api.utils.luma_cover.requests.get")
def test_no_request_without_an_event_embed(get):
    assert fetch_luma_cover(None) is None
    assert fetch_luma_cover("https://luma.com/embed/calendar/cal-x/events") is None
    get.assert_not_called()


# ── search document ──────────────────────────────────────────────────────


def event(**kwargs) -> Event:
    defaults = dict(name="Meetup", status=EventStatus.PUBLISHED, luma_embed={"src": EMBED})
    defaults.update(kwargs)
    return Event(**defaults)


@patch("search.documents.event_document.fetch_luma_cover", return_value=COVER)
def test_document_asks_luma_for_the_stored_embed(fetch):
    assert EventDocument().prepare(event())["cover_url"] == COVER
    fetch.assert_called_once_with(EMBED)


@patch("search.documents.event_document.fetch_luma_cover")
def test_document_asks_luma_on_every_build(fetch):
    """No value is carried over: each build (publish, edit, deploy populate) asks again."""
    doc, instance = EventDocument(), event()
    fetch.return_value = COVER
    assert doc.prepare(instance)["cover_url"] == COVER
    fetch.return_value = NEW_COVER
    assert doc.prepare(instance)["cover_url"] == NEW_COVER
    fetch.return_value = None
    assert doc.prepare(instance)["cover_url"] is None
    assert fetch.call_count == 3


@pytest.mark.parametrize("embed", [{}, None, "not a dict", {"src": None}])
def test_document_without_embed_has_null_cover(embed):
    with patch("api.utils.luma_cover.requests.get") as get:
        assert EventDocument().prepare(event(luma_embed=embed))["cover_url"] is None
        get.assert_not_called()


@patch("search.documents.event_document.fetch_luma_cover", return_value=COVER)
def test_document_does_not_carry_the_embed(fetch):
    prepared = EventDocument().prepare(event())
    assert "luma_embed" not in prepared
    assert EMBED not in json.dumps(prepared, default=str)
