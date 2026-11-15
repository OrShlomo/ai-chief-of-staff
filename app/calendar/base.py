"""Provider-agnostic calendar interface.

The agent talks only to CalendarProvider. Google is the first implementation;
Outlook (Microsoft Graph) can be added later without touching the agent (PRD: plan for both).
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


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
