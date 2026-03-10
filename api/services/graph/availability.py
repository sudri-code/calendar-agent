from datetime import datetime
from typing import Any

from api.services.graph.client import GraphClient


def _format_datetime(dt: datetime) -> str:
    return dt.isoformat()


async def get_schedule(
    account,
    emails: list[str],
    start: datetime,
    end: datetime,
    timezone: str = "UTC",
) -> dict:
    """Get free/busy schedule for a list of users."""
    async with GraphClient(account) as client:
        body = {
            "schedules": emails,
            "startTime": {
                "dateTime": _format_datetime(start),
                "timeZone": timezone,
            },
            "endTime": {
                "dateTime": _format_datetime(end),
                "timeZone": timezone,
            },
            "availabilityViewInterval": 30,
        }
        return await client.post("/me/calendar/getSchedule", json=body)
