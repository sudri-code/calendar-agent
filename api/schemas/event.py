import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel

from shared.schemas.event import EventDraft, EventPatch, AttendeeInfo, RecurrenceConfig


class EventResponse(BaseModel):
    id: uuid.UUID
    calendar_id: uuid.UUID
    external_event_id: str
    sync_group_id: uuid.UUID
    role: str
    status: str
    title: str
    description: Optional[str]
    start_at: datetime
    end_at: datetime
    timezone: str
    attendees_json: list[Any]
    is_recurrence_master: bool
    recurrence_rule: Optional[str]
    deleted_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AvailabilityRequest(BaseModel):
    start_at: datetime
    end_at: datetime
    attendee_emails: list[str] = []


class FindSlotsRequest(BaseModel):
    date_from: datetime
    date_to: datetime
    duration_minutes: int
    attendee_emails: list[str] = []
    preferred_time_from: Optional[str] = None
    preferred_time_to: Optional[str] = None


class CreateEventRequest(EventDraft):
    pass


class UpdateEventRequest(EventPatch):
    pass
