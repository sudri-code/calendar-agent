from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SlotRequest(BaseModel):
    user_id: str
    attendee_emails: list[str] = []
    date_from: datetime
    date_to: datetime
    duration_minutes: int
    preferred_time_from: Optional[str] = None  # HH:MM
    preferred_time_to: Optional[str] = None    # HH:MM


class TimeSlot(BaseModel):
    start_at: datetime
    end_at: datetime
    score: float = 0.0
    conflicts: list[str] = []
