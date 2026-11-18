"""Provider-agnostic calendar interface.

The agent talks only to CalendarProvider. Google is the first implementation;
Outlook (Microsoft Graph) can be added later without touching the agent (PRD: plan for both).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class CalendarEvent:
    calendar: str
    title: str
    start: str  # ISO 8601 date (all-day) or datetime
    end: str
    all_day: bool
    location: str | None = None
    status: str | None = None  # confirmed / tentative / cancelled


class CalendarProvider(Protocol):
    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...


def week_bounds(now: datetime, tz: str) -> tuple[datetime, datetime]:
    """Calendar week (Sunday 00:00 to next Sunday 00:00, local time) that contains `now`.

    Israeli convention: the week starts on Sunday. Computed in local time, because
    "Sunday" in UTC starts 2-3 hours late in Israel.
    """
    local = now.astimezone(ZoneInfo(tz))
    days_since_sunday = (local.weekday() + 1) % 7  # weekday(): Monday == 0, Sunday == 6
    start = (local - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7)
