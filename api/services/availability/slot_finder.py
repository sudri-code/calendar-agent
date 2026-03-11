import uuid
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from api.config import settings
from api.db.session import async_session_factory
from api.models.calendar import Calendar
from api.models.exchange_account import ExchangeAccount
from api.services.ews.availability import get_schedule


WORK_HOUR_START = 9   # 9:00
WORK_HOUR_END = 18    # 18:00
SLOT_INTERVAL = 30    # minutes
MAX_SLOTS = 8

_LOCAL_TZ = ZoneInfo(settings.ews_timezone)


def _to_local_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(_LOCAL_TZ).replace(tzinfo=None)


def _overlaps(s1: datetime, e1: datetime, s2: datetime, e2: datetime) -> bool:
    s1, e1 = _to_local_naive(s1), _to_local_naive(e1)
    s2, e2 = _to_local_naive(s2), _to_local_naive(e2)
    return s1 < e2 and s2 < e1


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

    # Load account
    async with async_session_factory() as session:
        result = await session.execute(
            select(Calendar, ExchangeAccount).join(
                ExchangeAccount, Calendar.account_id == ExchangeAccount.id
            ).where(
                Calendar.user_id == user_id,
                Calendar.is_active == True,
            )
        )
        rows = result.all()

    if not rows:
        return []

    _, account = rows[0]
    user_emails = list({acc.email for _, acc in rows})
    all_emails = list(dict.fromkeys(user_emails + attendee_emails))

    # Single EWS request for the entire range
    schedule_data = await get_schedule(account, all_emails, date_from, date_to)

    # Collect all busy intervals from all schedules
    busy_intervals: list[tuple[datetime, datetime]] = []
    for sched in schedule_data.get("value", []):
        for item in sched.get("scheduleItems", []):
            if item.get("status", "busy") == "free":
                continue
            try:
                s = datetime.fromisoformat(item["start"]["dateTime"])
                e = datetime.fromisoformat(item["end"]["dateTime"])
                busy_intervals.append((_to_local_naive(s), _to_local_naive(e)))
            except Exception:
                pass

    now = datetime.now(_LOCAL_TZ).replace(tzinfo=None)
    available_slots = []
    current = date_from.replace(hour=WORK_HOUR_START, minute=0, second=0, microsecond=0)
    if current < now:
        minutes_ahead = (now.minute // SLOT_INTERVAL + 1) * SLOT_INTERVAL
        current = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes_ahead)

    while current < date_to and len(available_slots) < MAX_SLOTS * 3:
        if current.hour < WORK_HOUR_START or current.hour >= WORK_HOUR_END:
            current = current.replace(hour=WORK_HOUR_START, minute=0) + timedelta(days=1)
            continue

        slot_end = current + timedelta(minutes=duration_minutes)
        if slot_end.hour > WORK_HOUR_END or (slot_end.hour == WORK_HOUR_END and slot_end.minute > 0):
            current = current.replace(hour=WORK_HOUR_START, minute=0) + timedelta(days=1)
            continue

        # Check locally against cached busy intervals
        is_free = not any(_overlaps(current, slot_end, bs, be) for bs, be in busy_intervals)
        if is_free:
            score = 0.0
            if pref_start_hour <= current.hour < pref_end_hour:
                score += 10.0
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

    available_slots.sort(key=lambda s: (-s["score"], s["start_at"]))
    return available_slots[:MAX_SLOTS]
