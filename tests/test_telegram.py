from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import main, telegram
from app.calendar.base import CalendarEvent, week_bounds
from app.main import app

SECRET = "hook-secret"
OWNER = 1111


def _update(sender_id: int, text: str = "/week") -> dict:
    return {"update_id": 1, "message": {"message_id": 1, "text": text,
                                        "from": {"id": sender_id}, "chat": {"id": sender_id, "type": "private"}}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("TELEGRAM_OWNER_ID", str(OWNER))
    for var, val in {"DATABASE_URL": "postgresql://u:p@h/db", "GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "cs",
                     "OAUTH_REDIRECT_URI": "https://x/cb", "TOKEN_ENCRYPTION_KEY": "k", "ADMIN_API_KEY": "a"}.items():
        monkeypatch.setenv(var, val)
    return TestClient(app)


def _post(c, body, secret=SECRET):
    return c.post("/telegram/webhook", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": secret})


def test_webhook_503_until_configured(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_OWNER_ID", raising=False)
    assert TestClient(app).post("/telegram/webhook", json=_update(OWNER)).status_code == 503


def test_webhook_rejects_bad_or_missing_secret(client):
    assert _post(client, _update(OWNER), secret="wrong").status_code == 403
    assert client.post("/telegram/webhook", json=_update(OWNER)).status_code == 403


def test_webhook_ignores_non_owner_silently(client, monkeypatch):
    monkeypatch.setattr(main, "fetch_week", lambda s: pytest.fail("calendar must not be read for strangers"))
    r = _post(client, _update(9999))
    assert r.status_code == 200 and r.json() == {}


def test_webhook_ignores_updates_without_message(client):
    r = _post(client, {"update_id": 2, "edited_message": {"from": {"id": OWNER}}})
    assert r.status_code == 200 and r.json() == {}


def test_owner_gets_week_as_reply(client, monkeypatch):
    start = datetime(2026, 11, 16, 7, 0, tzinfo=timezone.utc)  # Monday 09:00 in Israel
    events = [CalendarEvent("Me", "Workout", "2026-11-16T09:00:00+02:00", "2026-11-16T10:00:00+02:00", False)]
    monkeypatch.setattr(main, "fetch_week", lambda s: (start, start, events))
    r = _post(client, _update(OWNER, "hello"))  # any message works, not only /week
    body = r.json()
    assert r.status_code == 200
    assert body["method"] == "sendMessage" and body["chat_id"] == OWNER and body["parse_mode"] == "HTML"
    assert "Workout" in body["text"] and "09:00–10:00" in body["text"]


def test_owner_told_to_reconnect_when_token_expired(client, monkeypatch):
    def boom(s):
        raise main.CalendarNotConnected("expired")
    monkeypatch.setattr(main, "fetch_week", boom)
    r = _post(client, _update(OWNER))
    assert r.status_code == 200 and r.json()["text"] == telegram.RECONNECT


def test_unexpected_error_still_returns_200(client, monkeypatch):
    def boom(s):
        raise RuntimeError("db down postgresql://u:secret@h/db")
    monkeypatch.setattr(main, "fetch_week", boom)
    r = _post(client, _update(OWNER))
    assert r.status_code == 200 and r.json()["text"] == telegram.ERROR


def test_week_bounds_is_sunday_to_saturday_in_local_time():
    tz = "Asia/Jerusalem"
    # Wednesday 18.11 -> week of Sunday 15.11 00:00 local until Sunday 22.11 00:00 local
    start, end = week_bounds(datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc), tz)
    assert start.isoformat() == "2026-11-15T00:00:00+02:00" and end.isoformat() == "2026-11-22T00:00:00+02:00"
    # Saturday 23:30 UTC is already Sunday 01:30 in Israel -> the NEXT week starts
    start, _ = week_bounds(datetime(2026, 11, 21, 23, 30, tzinfo=timezone.utc), tz)
    assert start.date().isoformat() == "2026-11-22"
    # Sunday itself belongs to its own week
    start, _ = week_bounds(datetime(2026, 11, 15, 8, 0, tzinfo=timezone.utc), tz)
    assert start.date().isoformat() == "2026-11-15"


def test_format_week_groups_by_local_day_and_escapes():
    tz = "Asia/Jerusalem"
    start, _ = week_bounds(datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc), tz)
    now = datetime(2026, 11, 15, 23, 30, tzinfo=timezone.utc)  # already Monday 16.11 in Israel
    events = [
        CalendarEvent("Me", "Late <meeting>", "2026-11-17T18:00:00+02:00", "2026-11-17T19:00:00+02:00", False, "Tel Aviv"),
        CalendarEvent("Me", "Early", "2026-11-17T08:00:00+02:00", "2026-11-17T08:30:00+02:00", False),
        CalendarEvent("Holidays", "Holiday", "2026-11-17", "2026-11-18", True),
    ]
    text = telegram.format_week(events, start, now, tz)
    assert "<b>יום שני 16.11</b> (היום)" in text
    assert text.count("(היום)") == 1
    days = [line for line in text.splitlines() if line.startswith("<b>יום")]
    assert days[0].startswith("<b>יום ראשון 15.11") and days[-1].startswith("<b>יום שבת 21.11")
    tuesday = text.split("<b>יום שלישי 17.11</b>\n")[1].split("\n\n")[0].splitlines()
    assert tuesday == ["• כל היום  Holiday", "• 08:00–08:30  Early", "• 18:00–19:00  Late &lt;meeting&gt; (Tel Aviv)"]
    assert text.count("פנוי") == 6


def test_format_week_respects_telegram_length_limit():
    start = datetime(2026, 11, 16, 7, 0, tzinfo=timezone.utc)
    events = [CalendarEvent("Me", "x" * 100, "2026-11-16T09:00:00+02:00", "2026-11-16T10:00:00+02:00", False)] * 100
    assert len(telegram.format_week(events, start, start, "Asia/Jerusalem")) <= telegram.MAX_MESSAGE_CHARS
