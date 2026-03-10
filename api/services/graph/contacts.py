from typing import Any

from api.services.graph.client import GraphClient


async def list_contacts(account) -> list[dict]:
    """List all contacts with pagination."""
    contacts = []
    async with GraphClient(account) as client:
        url = "/me/contacts"
        params = {
            "$top": 100,
            "$select": "id,displayName,emailAddresses,mobilePhone,businessPhones",
        }

        while url:
            data = await client.get(url, params=params)
            contacts.extend(data.get("value", []))

            # Handle pagination
            next_link = data.get("@odata.nextLink")
            if next_link:
                # Extract path from full URL
                url = next_link.replace("https://graph.microsoft.com/v1.0", "")
                params = {}  # params already in URL
            else:
                url = None

    return contacts
