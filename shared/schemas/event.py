from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AttendeeInfo(BaseModel):
    name: Optional[str] = None
    email: str


class RecurrenceConfig(BaseModel):
    frequency: str  # daily, weekly, monthly, yearly
    interval: int = 1
    days_of_week: Optional[list[str]] = None  # MO, TU, WE, TH, FR, SA, SU
    end_type: str = "no_end"  # no_end, by_date, by_count
    end_date: Optional[str] = None  # ISO date string
    count: Optional[int] = None


class EventDraft(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str = "UTC"
    description: Optional[str] = None
    attendees: list[AttendeeInfo] = Field(default_factory=list)
    calendar_id: Optional[str] = None
    recurrence: Optional[RecurrenceConfig] = None


class RecurringEventDraft(EventDraft):
    recurrence: RecurrenceConfig


class EventPatch(BaseModel):
    title: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    description: Optional[str] = None
    attendees: Optional[list[AttendeeInfo]] = None
    recurrence_edit_mode: Optional[str] = None  # single, this_and_following, all
