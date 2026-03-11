from api.services.ews.client import EWSClient


async def list_contacts(account) -> list[dict]:
    async with EWSClient(account) as client:
        return await client.get_contacts()


async def resolve_names(account, query: str) -> list[dict]:
    """Search GAL + personal contacts via EWS ResolveNames."""
    async with EWSClient(account) as client:
        return await client.resolve_names(query)
