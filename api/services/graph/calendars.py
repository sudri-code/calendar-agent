from typing import Any

from api.services.graph.client import GraphClient


async def list_calendars(account) -> list[dict]:
    """List all calendars for an Exchange account."""
    async with GraphClient(account) as client:
        data = await client.get("/me/calendars", params={"$top": 100})
        return data.get("value", [])


async def get_calendar(account, calendar_id: str) -> dict:
    """Get a specific calendar."""
    async with GraphClient(account) as client:
        return await client.get(f"/me/calendars/{calendar_id}")
