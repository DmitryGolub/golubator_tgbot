"""Minimal async CalDAV client: discovery (PROPFIND), PUT and DELETE.

Only supports VEVENT calendars. No caching of ETags outside the caller. Uses
`httpx.AsyncClient` under the hood so the call sites can live inside the
worker event loop without any extra threading.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

NS = {
    "d": "DAV:",
    "c": "urn:ietf:params:xml:ns:caldav",
    "cs": "http://calendarserver.org/ns/",
}

_PROPFIND_PRINCIPAL = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:current-user-principal/>
  </d:prop>
</d:propfind>
""".strip()

_PROPFIND_HOME = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <c:calendar-home-set/>
  </d:prop>
</d:propfind>
""".strip()

_PROPFIND_CALENDARS = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:displayname/>
    <d:resourcetype/>
    <c:supported-calendar-component-set/>
  </d:prop>
</d:propfind>
""".strip()


class CalDAVError(Exception):
    """Base class for CalDAV client errors."""


class CalDAVAuthError(CalDAVError):
    """401/403 from the server."""


class CalDAVNotFoundError(CalDAVError):
    """404 from the server."""


class CalDAVConflictError(CalDAVError):
    """409/412 — precondition failed (If-Match mismatch)."""


class CalDAVTransientError(CalDAVError):
    """Network timeout, 5xx, DNS failure — retryable."""


@dataclass(frozen=True)
class CalendarInfo:
    url: str
    display_name: Optional[str]


@dataclass(frozen=True)
class DiscoveryResult:
    principal_url: str
    calendar_home_url: str
    calendars: list[CalendarInfo]


@dataclass(frozen=True)
class PutResult:
    href: str
    etag: Optional[str]


@dataclass(frozen=True)
class ChangedEvent:
    href: str
    etag: Optional[str]
    change_type: str  # "changed" | "deleted"


@dataclass(frozen=True)
class SyncCollectionResult:
    new_sync_token: str
    changes: list[ChangedEvent]
    invalid_token: bool  # True → caller must do full-scan via calendar-query


@dataclass(frozen=True)
class CalendarObject:
    href: str
    etag: Optional[str]
    calendar_data: bytes


def _normalize_etag(etag: Optional[str]) -> Optional[str]:
    if etag is None:
        return None
    return etag.strip().strip('"').strip("W/").strip('"') or None


def _absolutize(base: str, path: str) -> str:
    if not path:
        return base
    if path.startswith("http://") or path.startswith("https://"):
        return path
    # `urljoin` needs the base to have trailing slash to resolve relative parts
    return urljoin(base, path)


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status in (401, 403):
        raise CalDAVAuthError(f"auth failed: HTTP {status}")
    if status == 404:
        raise CalDAVNotFoundError("resource not found")
    if status in (409, 412):
        raise CalDAVConflictError(f"precondition failed: HTTP {status}")
    if status >= 500:
        raise CalDAVTransientError(f"server error: HTTP {status}")
    if status >= 400:
        raise CalDAVError(f"HTTP {status}")


class CalDAVClient:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._auth = (username, password)
        self._timeout = timeout

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            auth=self._auth,
            follow_redirects=True,
            timeout=self._timeout,
            headers={"User-Agent": "golubator-caldav/1.0"},
        )

    # ── Discovery ─────────────────────────────────────────────────────

    async def _propfind(
        self,
        client: httpx.AsyncClient,
        url: str,
        body: str,
        *,
        depth: str = "0",
    ) -> ET.Element:
        try:
            response = await client.request(
                "PROPFIND",
                url,
                content=body.encode("utf-8"),
                headers={
                    "Depth": depth,
                    "Content-Type": "application/xml; charset=utf-8",
                    "Prefer": "return=minimal",
                },
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise CalDAVTransientError(f"network error: {exc}") from exc
        _raise_for_status(response)
        try:
            return ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise CalDAVError(f"invalid XML response: {exc}") from exc

    def _extract_href(self, root: ET.Element, xpath: str) -> Optional[str]:
        el = root.find(xpath, NS)
        if el is None:
            return None
        href = el.findtext("d:href", namespaces=NS)
        return href.strip() if href else None

    async def discover(self) -> DiscoveryResult:
        async with self._build_client() as client:
            # Step 1: current-user-principal
            root = await self._propfind(
                client, self._base_url, _PROPFIND_PRINCIPAL, depth="0"
            )
            principal_path = self._extract_href(
                root,
                ".//d:response/d:propstat/d:prop/d:current-user-principal",
            )
            if not principal_path:
                raise CalDAVError("current-user-principal not found in PROPFIND")
            principal_url = _absolutize(self._base_url, principal_path)

            # Step 2: calendar-home-set
            root = await self._propfind(
                client, principal_url, _PROPFIND_HOME, depth="0"
            )
            home_path = self._extract_href(
                root,
                ".//d:response/d:propstat/d:prop/c:calendar-home-set",
            )
            if not home_path:
                raise CalDAVError("calendar-home-set not found in PROPFIND")
            home_url = _absolutize(principal_url, home_path)
            if not home_url.endswith("/"):
                home_url += "/"

            # Step 3: list calendars
            root = await self._propfind(
                client, home_url, _PROPFIND_CALENDARS, depth="1"
            )
            calendars: list[CalendarInfo] = []
            for resp in root.findall("d:response", NS):
                href = resp.findtext("d:href", namespaces=NS)
                if not href:
                    continue
                propstat = resp.find("d:propstat/d:prop", NS)
                if propstat is None:
                    continue
                resource_types = propstat.find("d:resourcetype", NS)
                if (
                    resource_types is None
                    or resource_types.find("c:calendar", NS) is None
                ):
                    continue
                comps = propstat.find("c:supported-calendar-component-set", NS)
                supports_vevent = False
                if comps is not None:
                    for comp in comps.findall("c:comp", NS):
                        if comp.attrib.get("name", "").upper() == "VEVENT":
                            supports_vevent = True
                            break
                else:
                    supports_vevent = True  # assume yes if server omits
                if not supports_vevent:
                    continue
                display_name = propstat.findtext("d:displayname", namespaces=NS)
                cal_url = _absolutize(home_url, href.strip())
                if not cal_url.endswith("/"):
                    cal_url += "/"
                calendars.append(
                    CalendarInfo(
                        url=cal_url,
                        display_name=(display_name or None),
                    )
                )
            return DiscoveryResult(
                principal_url=principal_url,
                calendar_home_url=home_url,
                calendars=calendars,
            )

    async def verify(self) -> DiscoveryResult:
        result = await self.discover()
        if not result.calendars:
            raise CalDAVError("no VEVENT calendars found for this account")
        return result

    # ── Event CRUD ────────────────────────────────────────────────────

    async def put_event(
        self,
        *,
        calendar_url: str,
        uid: str,
        ics: bytes,
        etag: Optional[str] = None,
    ) -> PutResult:
        url = calendar_url.rstrip("/") + "/" + uid + ".ics"
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        if etag:
            headers["If-Match"] = f'"{etag}"'
        async with self._build_client() as client:
            try:
                response = await client.put(url, content=ics, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise CalDAVTransientError(f"network error: {exc}") from exc
            if response.status_code not in (200, 201, 204):
                _raise_for_status(response)
            new_etag = _normalize_etag(response.headers.get("ETag"))
            return PutResult(href=url, etag=new_etag)

    async def delete_event(self, *, href: str, etag: Optional[str] = None) -> None:
        headers: dict[str, str] = {}
        if etag:
            headers["If-Match"] = f'"{etag}"'
        async with self._build_client() as client:
            try:
                response = await client.delete(href, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise CalDAVTransientError(f"network error: {exc}") from exc
            if response.status_code in (200, 204, 404):
                return
            _raise_for_status(response)

    # ── Pull (RFC 6578 sync-collection + CTag fallback) ───────────────

    async def sync_collection(
        self, calendar_url: str, sync_token: Optional[str]
    ) -> SyncCollectionResult:
        token_xml = (
            f"<d:sync-token>{_xml_escape(sync_token)}</d:sync-token>"
            if sync_token
            else "<d:sync-token/>"
        )
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<d:sync-collection xmlns:d="DAV:">
  {token_xml}
  <d:sync-level>1</d:sync-level>
  <d:prop>
    <d:getetag/>
  </d:prop>
</d:sync-collection>""".strip()

        async with self._build_client() as client:
            try:
                response = await client.request(
                    "REPORT",
                    calendar_url,
                    content=body.encode("utf-8"),
                    headers={
                        "Depth": "1",
                        "Content-Type": "application/xml; charset=utf-8",
                    },
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise CalDAVTransientError(f"network error: {exc}") from exc

            # Server lost the token → caller must do a full-scan rebuild.
            if response.status_code in (403, 410):
                if _has_valid_sync_token_error(response.content):
                    return SyncCollectionResult(
                        new_sync_token="", changes=[], invalid_token=True
                    )
                if response.status_code == 410:
                    return SyncCollectionResult(
                        new_sync_token="", changes=[], invalid_token=True
                    )
                _raise_for_status(response)

            _raise_for_status(response)

            try:
                root = ET.fromstring(response.content)
            except ET.ParseError as exc:
                raise CalDAVError(f"invalid XML response: {exc}") from exc

            if _has_valid_sync_token_error(response.content):
                return SyncCollectionResult(
                    new_sync_token="", changes=[], invalid_token=True
                )

            new_token = root.findtext("d:sync-token", default="", namespaces=NS) or ""

            changes: list[ChangedEvent] = []
            for resp in root.findall("d:response", NS):
                href = resp.findtext("d:href", namespaces=NS)
                if not href:
                    continue
                href = href.strip()
                # Top-level status (deletions): "HTTP/1.1 404 Not Found"
                top_status = resp.findtext("d:status", namespaces=NS) or ""
                if "404" in top_status:
                    changes.append(
                        ChangedEvent(href=href, etag=None, change_type="deleted")
                    )
                    continue
                etag = None
                for propstat in resp.findall("d:propstat", NS):
                    status = propstat.findtext("d:status", namespaces=NS) or ""
                    if "200" not in status:
                        continue
                    raw_etag = propstat.findtext("d:prop/d:getetag", namespaces=NS)
                    etag = _normalize_etag(raw_etag)
                changes.append(
                    ChangedEvent(href=href, etag=etag, change_type="changed")
                )
            return SyncCollectionResult(
                new_sync_token=new_token.strip(),
                changes=changes,
                invalid_token=False,
            )

    async def get_ctag(self, calendar_url: str) -> Optional[str]:
        body = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:cs="http://calendarserver.org/ns/">
  <d:prop>
    <cs:getctag/>
  </d:prop>
</d:propfind>""".strip()
        async with self._build_client() as client:
            root = await self._propfind(client, calendar_url, body, depth="0")
        ctag = root.findtext(
            ".//d:response/d:propstat/d:prop/cs:getctag", namespaces=NS
        )
        return ctag.strip() if ctag else None

    async def calendar_query(
        self, calendar_url: str, uid_prefix: str
    ) -> list[CalendarObject]:
        # We request all VEVENT objects with calendar-data + etag, then
        # filter UIDs client-side. This is more portable than `text-match`,
        # which iCloud and some Radicale builds support inconsistently.
        body = """<?xml version="1.0" encoding="utf-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag/>
    <c:calendar-data/>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT"/>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>""".strip()

        async with self._build_client() as client:
            try:
                response = await client.request(
                    "REPORT",
                    calendar_url,
                    content=body.encode("utf-8"),
                    headers={
                        "Depth": "1",
                        "Content-Type": "application/xml; charset=utf-8",
                    },
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise CalDAVTransientError(f"network error: {exc}") from exc
            _raise_for_status(response)

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise CalDAVError(f"invalid XML response: {exc}") from exc

        results: list[CalendarObject] = []
        prefix_token = f"UID:{uid_prefix}"
        for resp in root.findall("d:response", NS):
            href = resp.findtext("d:href", namespaces=NS)
            if not href:
                continue
            etag = None
            data = None
            for propstat in resp.findall("d:propstat", NS):
                status = propstat.findtext("d:status", namespaces=NS) or ""
                if "200" not in status:
                    continue
                raw_etag = propstat.findtext("d:prop/d:getetag", namespaces=NS)
                etag = _normalize_etag(raw_etag)
                data = propstat.findtext("d:prop/c:calendar-data", namespaces=NS)
            if data is None:
                continue
            data_bytes = data.encode("utf-8")
            # Cheap pre-filter: keep only objects whose UID starts with our prefix.
            if prefix_token.encode("utf-8") not in data_bytes:
                continue
            results.append(
                CalendarObject(
                    href=href.strip(),
                    etag=etag,
                    calendar_data=data_bytes,
                )
            )
        return results

    async def get_event(self, href: str) -> tuple[bytes, Optional[str]]:
        async with self._build_client() as client:
            try:
                response = await client.get(href)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise CalDAVTransientError(f"network error: {exc}") from exc
            _raise_for_status(response)
            return response.content, _normalize_etag(response.headers.get("ETag"))


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _has_valid_sync_token_error(content: bytes) -> bool:
    # RFC 6578 §3.8: <DAV:valid-sync-token/> in <DAV:error/>
    return b"valid-sync-token" in content


# Expose host-extraction helper used by callers for logging/UID formatting
def parse_hostname(url: str) -> str:
    return urlparse(url).hostname or ""
