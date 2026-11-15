import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
from cryptography.fernet import Fernet

from app import security
from app.calendar import google

KEY = Fernet.generate_key().decode()


def test_encrypt_roundtrip():
    assert security.decrypt(KEY, security.encrypt(KEY, "refresh-123")) == "refresh-123"


def test_state_valid_and_tamper_and_expiry():
    st = security.sign_state(KEY, now=1000)
    assert security.verify_state(KEY, st, now=1100)
    assert not security.verify_state(KEY, st + "x", now=1100)
    assert not security.verify_state(KEY, st, now=1000 + 601)
    assert not security.verify_state(Fernet.generate_key().decode(), st, now=1100)


def test_auth_url_requests_readonly_offline_access():
    url = google.build_auth_url("cid", "https://x/cb", ["https://www.googleapis.com/auth/calendar.readonly"], "st")
    q = parse_qs(urlparse(url).query)
    assert q["access_type"] == ["offline"]
    assert q["scope"] == ["https://www.googleapis.com/auth/calendar.readonly"]
    assert q["state"] == ["st"]


def test_provider_reads_selected_calendars_and_skips_cancelled():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer at"
        if request.url.path.endswith("/calendarList"):
            return httpx.Response(200, json={"items": [
                {"id": "primary@x", "summary": "Me", "selected": True},
                {"id": "hidden@x", "summary": "Hidden", "selected": False},
            ]})
        assert "primary" in request.url.path
        return httpx.Response(200, json={"items": [
            {"summary": "Workout", "status": "confirmed",
             "start": {"dateTime": "2026-11-16T09:00:00+02:00"}, "end": {"dateTime": "2026-11-16T10:00:00+02:00"}},
            {"summary": "Gone", "status": "cancelled",
             "start": {"dateTime": "2026-11-16T11:00:00+02:00"}, "end": {"dateTime": "2026-11-16T12:00:00+02:00"}},
            {"summary": "Flowers", "start": {"date": "2026-11-20"}, "end": {"date": "2026-11-21"}},
        ]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    events = google.GoogleCalendarProvider(client, "at", "Asia/Jerusalem").list_events(now, now + timedelta(days=7))
    assert [e.title for e in events] == ["Workout", "Flowers"]
    assert events[1].all_day is True
    assert events[0].calendar == "Me"


def test_endpoints_return_503_until_configured(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    for var in ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OAUTH_REDIRECT_URI", "TOKEN_ENCRYPTION_KEY", "ADMIN_API_KEY"]:
        monkeypatch.delenv(var, raising=False)
    c = TestClient(app)
    assert c.get("/calendar/week").status_code == 503
    assert c.get("/oauth/google/start").status_code == 503


def test_start_requires_admin_key(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "cs")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "https://x/oauth/google/callback")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", KEY)
    monkeypatch.setenv("ADMIN_API_KEY", "admin")
    c = TestClient(app, follow_redirects=False)
    assert c.get("/oauth/google/start?key=wrong").status_code == 403
    r = c.get("/oauth/google/start?key=admin")
    assert r.status_code == 307 and r.headers["location"].startswith("https://accounts.google.com/")
    assert c.get("/calendar/week", headers={"X-Admin-Key": "wrong"}).status_code == 403


def test_calendar_ids_with_hash_are_url_encoded_and_failures_skipped():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/calendarList"):
            return httpx.Response(200, json={"items": [
                {"id": "iw.jewish#holiday@group.v.calendar.google.com", "summary": "Holidays", "selected": True},
                {"id": "broken@x", "summary": "Broken", "selected": True},
            ]})
        seen.append(request.url.raw_path.decode())
        if "broken" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, json={"items": [
            {"summary": "Holiday", "start": {"date": "2026-11-18"}, "end": {"date": "2026-11-19"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    events = google.GoogleCalendarProvider(client, "at", "Asia/Jerusalem").list_events(now, now + timedelta(days=7))
    assert any("%23holiday" in p for p in seen)
    assert [e.title for e in events] == ["Holiday"]
