"""Telegram bot: message texts and formatting of the week (Hebrew, RTL-friendly).

Formatting uses Telegram HTML parse mode: only <b> tags, everything else escaped,
so event titles with '<' or '&' can't break the message.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from app.calendar.base import CalendarEvent

# date.weekday(): Monday == 0
HEBREW_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
MAX_MESSAGE_CHARS = 4096  # Telegram limit per message

NOT_CONFIGURED = "חיבור ליומן Google עדיין לא הוגדר בשרת."
RECONNECT = "החיבור ל-Google Calendar פג או בוטל. צריך להתחבר מחדש דרך הקישור /oauth/google/start."
ERROR = "משהו השתבש בקריאת היומן. נסה שוב בעוד דקה."


def _hhmm(iso: str) -> str:
    # Google returns dateTime in the timeZone we requested, so the wall-clock time is already local.
    return datetime.fromisoformat(iso).strftime("%H:%M")


def _event_line(e: CalendarEvent) -> str:
    when = "כל היום" if e.all_day else f"{_hhmm(e.start)}–{_hhmm(e.end)}"
    line = f"• {when}  {escape(e.title)}"
    if e.location:
        line += f" ({escape(e.location)})"
    return line


def format_week(events: list[CalendarEvent], start: datetime, tz: str) -> str:
    """One block per day for the 7 days starting today (local date), free days included."""
    first_day = start.astimezone(ZoneInfo(tz)).date()
    by_day: dict[date, list[CalendarEvent]] = defaultdict(list)
    for e in events:
        by_day[date.fromisoformat(e.start[:10])].append(e)

    blocks = [f"<b>📅 השבוע שלך</b> ({len(events)} אירועים)"]
    for i in range(7):
        d = first_day + timedelta(days=i)
        header = f"<b>יום {HEBREW_DAYS[d.weekday()]} {d.day}.{d.month}</b>"
        if i == 0:
            header += " (היום)"
        day_events = sorted(by_day.get(d, []), key=lambda e: (not e.all_day, e.start))
        lines = [_event_line(e) for e in day_events] or ["פנוי"]
        blocks.append("\n".join([header, *lines]))
    text = "\n\n".join(blocks)
    if len(text) > MAX_MESSAGE_CHARS:
        # Cut at a line boundary so no HTML tag is left open.
        text = text[: MAX_MESSAGE_CHARS - 20].rsplit("\n", 1)[0] + "\n…"
    return text


def reply(chat_id: int, text: str) -> dict:
    """Webhook response body that makes Telegram send `text` to `chat_id`."""
    return {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
