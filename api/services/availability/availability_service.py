import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import async_session_factory
from api.models.calendar import Calendar
from api.models.exchange_account import ExchangeAccount
from api.services.ews.availability import get_schedule


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
            if item.get("status") in ("busy", "tentative", "oof"):
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
