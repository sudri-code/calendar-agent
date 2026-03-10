from api.services.ews.client import EWSClient


async def list_calendars(account) -> list[dict]:
    async with EWSClient(account) as client:
        return await client.get_calendars()
