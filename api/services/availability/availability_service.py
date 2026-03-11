import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import async_session_factory
from api.models.calendar import Calendar
from api.models.exchange_account import ExchangeAccount
from api.services.ews.availability import get_schedule


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _overlaps(
    s1: datetime,
    e1: datetime,
    s2: datetime,
    e2: datetime,
) -> bool:
    """
    Return True if two intervals [s1, e1) and [s2, e2) overlap.

    Adjacent intervals where one ends exactly when the other starts
    (e.g. 12:30–15:00 and 15:00–16:00) are treated as NON-overlapping.
    """
    s1 = s1.replace(tzinfo=None)
    e1 = e1.replace(tzinfo=None)
    s2 = s2.replace(tzinfo=None)
    e2 = e2.replace(tzinfo=None)
    return s1 < e2 and s2 < e1


async def check_slot(
    user_id: uuid.UUID,
    start: datetime,
    end: datetime,
    attendee_emails: list[str],
) -> dict:
    """Check availability for a time slot across all calendars and attendees."""
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
        return {"available": True, "conflicts": []}

    # Use the first account to query
    _, account = rows[0]

    # Collect all emails to check
    user_emails = [acc.email for _, acc in rows]
    all_emails = list(set(user_emails + attendee_emails))

    schedule_data = await get_schedule(account, all_emails, start, end)
    schedules = schedule_data.get("value", [])

    conflicts = []
    for sched in schedules:
        for item in sched.get("scheduleItems", []):
            if item.get("status") not in ("busy", "tentative", "oof"):
                continue

            item_start = _parse_dt(item.get("start", {}).get("dateTime"))
            item_end = _parse_dt(item.get("end", {}).get("dateTime"))
            if not item_start or not item_end:
                continue

            # Filter out slots that only touch the boundary of the planned meeting
            if not _overlaps(start, end, item_start, item_end):
                continue

            conflicts.append({
                "email": sched.get("scheduleId"),
                "start": item.get("start", {}).get("dateTime"),
                "end": item.get("end", {}).get("dateTime"),
                "status": item.get("status"),
            })

    return {
        "available": len(conflicts) == 0,
        "conflicts": conflicts,
    }
