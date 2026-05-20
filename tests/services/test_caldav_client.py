"""Unit tests for src.services.caldav.client — mocked via httpx.MockTransport."""

from __future__ import annotations

import pytest
import httpx

from src.services.caldav import client as caldav_client
from src.services.caldav.client import (
    CalDAVAuthError,
    CalDAVClient,
    CalDAVConflictError,
    CalDAVTransientError,
    _normalize_etag,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


def _icloud_principal_xml(principal_path: str) -> str:
    return f"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/</d:href>
    <d:propstat>
      <d:prop>
        <d:current-user-principal>
          <d:href>{principal_path}</d:href>
        </d:current-user-principal>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>""".strip()


def _home_xml(home_path: str) -> str:
    return f"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:propstat>
      <d:prop>
        <c:calendar-home-set>
          <d:href>{home_path}</d:href>
        </c:calendar-home-set>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>""".strip()


def _calendars_xml(calendar_href: str, name: str = "Home") -> str:
    return f"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>{calendar_href}</d:href>
    <d:propstat>
      <d:prop>
        <d:displayname>{name}</d:displayname>
        <d:resourcetype><d:collection/><c:calendar/></d:resourcetype>
        <c:supported-calendar-component-set>
          <c:comp name="VEVENT"/>
        </c:supported-calendar-component-set>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>""".strip()


def _install_transport(monkeypatch, handler):
    """Patch `CalDAVClient._build_client` to return an httpx client backed by `handler`."""

    def _patched(self):
        return httpx.AsyncClient(
            auth=self._auth,
            follow_redirects=True,
            timeout=self._timeout,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(caldav_client.CalDAVClient, "_build_client", _patched)


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────


async def test_discover_icloud_like(monkeypatch):
    principal = "/1234567/principal/"
    home = "/1234567/calendars/"
    calendar_href = "/1234567/calendars/home/"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "PROPFIND" and url == "https://caldav.icloud.com/":
            return httpx.Response(207, content=_icloud_principal_xml(principal))
        if (
            request.method == "PROPFIND"
            and url == f"https://caldav.icloud.com{principal}"
        ):
            return httpx.Response(207, content=_home_xml(home))
        if request.method == "PROPFIND" and url == f"https://caldav.icloud.com{home}":
            return httpx.Response(
                207, content=_calendars_xml(calendar_href, name="Home")
            )
        return httpx.Response(404)

    _install_transport(monkeypatch, handler)

    client = CalDAVClient(
        base_url="https://caldav.icloud.com",
        username="u@example.com",
        password="pw",
    )
    result = await client.discover()
    assert result.principal_url.endswith(principal)
    assert result.calendar_home_url.endswith("/")
    assert len(result.calendars) == 1
    assert result.calendars[0].display_name == "Home"


async def test_put_event_returns_href_and_etag(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            assert request.headers["Content-Type"].startswith("text/calendar")
            return httpx.Response(201, headers={"ETag": '"abc123"'})
        return httpx.Response(404)

    _install_transport(monkeypatch, handler)

    client = CalDAVClient(
        base_url="https://caldav.example.com", username="u", password="p"
    )
    result = await client.put_event(
        calendar_url="https://caldav.example.com/u/home",
        uid="golubator-meeting-1@x",
        ics=b"BEGIN:VCALENDAR\r\n",
        etag=None,
    )
    # UID is percent-encoded in the href so that it matches the form
    # most CalDAV servers return in subsequent calendar-query responses.
    assert result.href.endswith("/golubator-meeting-1%40x.ics")
    assert result.etag == "abc123"


async def test_put_event_precondition_conflict(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        return httpx.Response(412)

    _install_transport(monkeypatch, handler)

    client = CalDAVClient(
        base_url="https://caldav.example.com", username="u", password="p"
    )
    with pytest.raises(CalDAVConflictError):
        await client.put_event(
            calendar_url="https://caldav.example.com/u/home",
            uid="x",
            ics=b"",
            etag="stale",
        )


async def test_auth_error_on_401(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    _install_transport(monkeypatch, handler)

    client = CalDAVClient(
        base_url="https://caldav.example.com", username="u", password="p"
    )
    with pytest.raises(CalDAVAuthError):
        await client.put_event(
            calendar_url="https://caldav.example.com/u/home",
            uid="x",
            ics=b"",
        )


async def test_delete_event_404_is_graceful(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(404)

    _install_transport(monkeypatch, handler)

    client = CalDAVClient(
        base_url="https://caldav.example.com", username="u", password="p"
    )
    # Does not raise
    await client.delete_event(
        href="https://caldav.example.com/u/home/missing.ics", etag=None
    )


async def test_transient_error_on_500(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    _install_transport(monkeypatch, handler)

    client = CalDAVClient(
        base_url="https://caldav.example.com", username="u", password="p"
    )
    with pytest.raises(CalDAVTransientError):
        await client.put_event(
            calendar_url="https://caldav.example.com/u/home",
            uid="x",
            ics=b"",
        )


def test_normalize_etag():
    assert _normalize_etag(None) is None
    assert _normalize_etag('"abc"') == "abc"
    assert _normalize_etag("abc") == "abc"
    assert _normalize_etag('W/"abc"') == "abc"
