"""Google Calendar implementation of CalendarProvider (OAuth 2.0 + REST)."""
from datetime import datetime
import logging
from urllib.parse import quote, urlencode

import httpx

from app.calendar.base import CalendarEvent

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"

log = logging.getLogger("cos.calendar")


def build_auth_url(client_id: str, redirect_uri: str, scopes: list[str], state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "access_type": "offline",  # ask for a refresh token
        "prompt": "consent",  # always return a refresh token, even on re-consent
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(client: httpx.Client, client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    r = client.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    r.raise_for_status()
    return r.json()


def refresh_access_token(client: httpx.Client, client_id: str, client_secret: str, refresh_token: str) -> str:
    r = client.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    r.raise_for_status()
    return r.json()["access_token"]


class GoogleCalendarProvider:
    def __init__(self, client: httpx.Client, access_token: str, timezone: str):
        self._client = client
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._tz = timezone

    def _selected_calendars(self) -> list[dict]:
        r = self._client.get(f"{API}/users/me/calendarList", headers=self._headers, params={"minAccessRole": "reader"})
        r.raise_for_status()
        # Only calendars the user shows in Google Calendar (e.g. primary + shared business calendar).
        return [c for c in r.json().get("items", []) if c.get("selected")]

    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for cal in self._selected_calendars():
            page_token = None
            while True:
                params = {
                    "timeMin": start.isoformat(),
                    "timeMax": end.isoformat(),
                    "singleEvents": "true",  # expand recurring series into occurrences
                    "orderBy": "startTime",
                    "timeZone": self._tz,
                    "maxResults": 250,
                }
                if page_token:
                    params["pageToken"] = page_token
                # Calendar IDs can contain '#' (e.g. holiday calendars) -> must be URL-encoded,
                # otherwise everything after '#' is treated as a URL fragment.
                cal_path = quote(cal["id"], safe="")
                r = self._client.get(f"{API}/calendars/{cal_path}/events", headers=self._headers, params=params)
                if r.status_code >= 400:
                    # One broken calendar must not hide the whole week.
                    log.warning("skipping calendar %s: HTTP %s", cal.get("summary", "?"), r.status_code)
                    break
                body = r.json()
                for e in body.get("items", []):
                    if e.get("status") == "cancelled":
                        continue
                    all_day = "date" in e.get("start", {})
                    events.append(
                        CalendarEvent(
                            calendar=cal.get("summaryOverride") or cal.get("summary", cal["id"]),
                            title=e.get("summary", "(no title)"),
                            start=e["start"].get("date") or e["start"].get("dateTime"),
                            end=e["end"].get("date") or e["end"].get("dateTime"),
                            all_day=all_day,
                            location=e.get("location"),
                            status=e.get("status"),
                        )
                    )
                page_token = body.get("nextPageToken")
                if not page_token:
                    break
        return sorted(events, key=lambda ev: ev.start)
