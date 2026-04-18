"""Unit tests for CalDAVClient pull-side methods (sync_collection, get_ctag,
calendar_query, get_event)."""

from __future__ import annotations

import httpx
import pytest

from src.services.caldav import client as caldav_client
from src.services.caldav.client import (
    CalDAVClient,
    CalDAVNotFoundError,
    CalDAVTransientError,
)


def _install_transport(monkeypatch, handler):
    def _patched(self):
        return httpx.AsyncClient(
            auth=self._auth,
            follow_redirects=True,
            timeout=self._timeout,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(caldav_client.CalDAVClient, "_build_client", _patched)


SYNC_COLLECTION_OK = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/cal/event-1.ics</d:href>
    <d:propstat>
      <d:prop>
        <d:getetag>"abc"</d:getetag>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/cal/event-2.ics</d:href>
    <d:status>HTTP/1.1 404 Not Found</d:status>
  </d:response>
  <d:sync-token>http://example.com/sync/2</d:sync-token>
</d:multistatus>"""


async def test_sync_collection_initial(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "REPORT"
        assert request.headers["Depth"] == "1"
        return httpx.Response(207, content=SYNC_COLLECTION_OK)

    _install_transport(monkeypatch, handler)
    client = CalDAVClient(base_url="https://x", username="u", password="p")
    result = await client.sync_collection("https://x/cal/", None)
    assert result.invalid_token is False
    assert result.new_sync_token == "http://example.com/sync/2"
    changed = [c for c in result.changes if c.change_type == "changed"]
    deleted = [c for c in result.changes if c.change_type == "deleted"]
    assert len(changed) == 1
    assert changed[0].href == "/cal/event-1.ics"
    assert changed[0].etag == "abc"
    assert len(deleted) == 1
    assert deleted[0].href == "/cal/event-2.ics"


SYNC_COLLECTION_INVALID = """<?xml version="1.0"?>
<d:error xmlns:d="DAV:"><d:valid-sync-token/></d:error>"""


async def test_sync_collection_invalid_token_410(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, content=SYNC_COLLECTION_INVALID)

    _install_transport(monkeypatch, handler)
    client = CalDAVClient(base_url="https://x", username="u", password="p")
    result = await client.sync_collection("https://x/cal/", "stale-token")
    assert result.invalid_token is True
    assert result.changes == []


async def test_sync_collection_invalid_token_403_with_marker(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=SYNC_COLLECTION_INVALID)

    _install_transport(monkeypatch, handler)
    client = CalDAVClient(base_url="https://x", username="u", password="p")
    result = await client.sync_collection("https://x/cal/", "stale-token")
    assert result.invalid_token is True


CTAG_XML = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:cs="http://calendarserver.org/ns/">
  <d:response>
    <d:href>/cal/</d:href>
    <d:propstat>
      <d:prop>
        <cs:getctag>tok-123</cs:getctag>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>"""


async def test_get_ctag(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PROPFIND"
        assert request.headers["Depth"] == "0"
        return httpx.Response(207, content=CTAG_XML)

    _install_transport(monkeypatch, handler)
    client = CalDAVClient(base_url="https://x", username="u", password="p")
    ctag = await client.get_ctag("https://x/cal/")
    assert ctag == "tok-123"


CALENDAR_QUERY_XML = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>/cal/ours.ics</d:href>
    <d:propstat>
      <d:prop>
        <d:getetag>"e1"</d:getetag>
        <c:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:golubator-meeting-9@x
DTSTART:20260101T120000Z
END:VEVENT
END:VCALENDAR
</c:calendar-data>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/cal/foreign.ics</d:href>
    <d:propstat>
      <d:prop>
        <d:getetag>"e2"</d:getetag>
        <c:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:foreign-event@y
DTSTART:20260101T120000Z
END:VEVENT
END:VCALENDAR
</c:calendar-data>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>"""


async def test_calendar_query_filters_by_uid_prefix(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "REPORT"
        return httpx.Response(207, content=CALENDAR_QUERY_XML)

    _install_transport(monkeypatch, handler)
    client = CalDAVClient(base_url="https://x", username="u", password="p")
    objs = await client.calendar_query("https://x/cal/", "golubator-meeting-")
    assert len(objs) == 1
    assert objs[0].href == "/cal/ours.ics"
    assert objs[0].etag == "e1"
    assert b"golubator-meeting-9" in objs[0].calendar_data


async def test_get_event_returns_body_and_etag(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200, content=b"BEGIN:VCALENDAR\r\n", headers={"ETag": '"xyz"'}
        )

    _install_transport(monkeypatch, handler)
    client = CalDAVClient(base_url="https://x", username="u", password="p")
    body, etag = await client.get_event("https://x/cal/e.ics")
    assert body == b"BEGIN:VCALENDAR\r\n"
    assert etag == "xyz"


async def test_get_event_404(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _install_transport(monkeypatch, handler)
    client = CalDAVClient(base_url="https://x", username="u", password="p")
    with pytest.raises(CalDAVNotFoundError):
        await client.get_event("https://x/cal/missing.ics")


async def test_get_event_5xx_transient(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    _install_transport(monkeypatch, handler)
    client = CalDAVClient(base_url="https://x", username="u", password="p")
    with pytest.raises(CalDAVTransientError):
        await client.get_event("https://x/cal/e.ics")
