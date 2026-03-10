from datetime import datetime
from typing import Any, Optional

from api.services.graph.client import GraphClient


def _format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


async def list_events(account, calendar_id: str, start: datetime, end: datetime) -> list[dict]:
    """List events in a calendar within a date range."""
    async with GraphClient(account) as client:
        data = await client.get(
            f"/me/calendars/{calendar_id}/calendarView",
            params={
                "startDateTime": _format_datetime(start),
                "endDateTime": _format_datetime(end),
                "$top": 100,
                "$orderby": "start/dateTime",
            },
        )
        return data.get("value", [])


async def create_event(account, calendar_id: str, event_body: dict) -> dict:
    """Create an event in a calendar."""
    async with GraphClient(account) as client:
        return await client.post(
            f"/me/calendars/{calendar_id}/events",
            json=event_body,
        )


async def update_event(account, calendar_id: str, event_id: str, patch_body: dict) -> dict:
    """Update an event."""
    async with GraphClient(account) as client:
        return await client.patch(
            f"/me/calendars/{calendar_id}/events/{event_id}",
            json=patch_body,
        )


async def delete_event(account, calendar_id: str, event_id: str) -> None:
    """Delete an event."""
    async with GraphClient(account) as client:
        await client.delete(f"/me/calendars/{calendar_id}/events/{event_id}")


async def get_event(account, calendar_id: str, event_id: str) -> dict:
    """Get a specific event."""
    async with GraphClient(account) as client:
        return await client.get(f"/me/calendars/{calendar_id}/events/{event_id}")


async def get_occurrence_list(account, series_master_id: str, start: datetime, end: datetime) -> list[dict]:
    """Get occurrences of a recurring event series."""
    async with GraphClient(account) as client:
        data = await client.get(
            f"/me/events/{series_master_id}/instances",
            params={
                "startDateTime": _format_datetime(start),
                "endDateTime": _format_datetime(end),
                "$top": 100,
            },
        )
        return data.get("value", [])
