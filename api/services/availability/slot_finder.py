import uuid
from datetime import datetime, timedelta
from typing import Optional

from api.services.availability.availability_service import check_slot


WORK_HOUR_START = 9   # 9:00
WORK_HOUR_END = 18    # 18:00
SLOT_INTERVAL = 30    # minutes
MAX_SLOTS = 8


async def find_slots(
    user_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
    duration_minutes: int,
    attendee_emails: list[str] = None,
    preferred_time_from: Optional[str] = None,  # HH:MM
    preferred_time_to: Optional[str] = None,    # HH:MM
) -> list[dict]:
    """Find available time slots within a date range."""
    attendee_emails = attendee_emails or []

    # Parse preferred time
    pref_start_hour = WORK_HOUR_START
    pref_end_hour = WORK_HOUR_END
    if preferred_time_from:
        h, m = map(int, preferred_time_from.split(":"))
        pref_start_hour = h
    if preferred_time_to:
        h, m = map(int, preferred_time_to.split(":"))
        pref_end_hour = h

    available_slots = []
    current = date_from.replace(hour=WORK_HOUR_START, minute=0, second=0, microsecond=0)

    while current < date_to and len(available_slots) < MAX_SLOTS * 3:
        # Skip outside working hours
        if current.hour < WORK_HOUR_START or current.hour >= WORK_HOUR_END:
            # Jump to next day working hours start
            current = current.replace(hour=WORK_HOUR_START, minute=0) + timedelta(days=1)
            continue

        slot_end = current + timedelta(minutes=duration_minutes)
        if slot_end.hour > WORK_HOUR_END or (slot_end.hour == WORK_HOUR_END and slot_end.minute > 0):
            # Jump to next day
            current = current.replace(hour=WORK_HOUR_START, minute=0) + timedelta(days=1)
            continue

        # Check availability
        result = await check_slot(user_id, current, slot_end, attendee_emails)
        if result["available"]:
            # Score: prefer slots in preferred time range
            score = 0.0
            if pref_start_hour <= current.hour < pref_end_hour:
                score += 10.0
            # Prefer morning
            if current.hour <= 12:
                score += 2.0
            elif current.hour <= 15:
                score += 1.0

            available_slots.append({
                "start_at": current.isoformat(),
                "end_at": slot_end.isoformat(),
                "score": score,
                "conflicts": [],
            })

        current += timedelta(minutes=SLOT_INTERVAL)

    # Sort by score descending, then by datetime
    available_slots.sort(key=lambda s: (-s["score"], s["start_at"]))
    return available_slots[:MAX_SLOTS]
