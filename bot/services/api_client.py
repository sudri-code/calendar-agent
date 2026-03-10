from typing import Any, Optional
import httpx

from bot.config import bot_settings


class BotClient:
    """HTTP client for bot-to-API communication."""

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=bot_settings.api_base_url,
            headers={
                "X-Internal-Key": bot_settings.internal_api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def get(self, path: str, **kwargs) -> dict:
        resp = await self._client.get(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def post(self, path: str, **kwargs) -> dict:
        resp = await self._client.post(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def patch(self, path: str, **kwargs) -> dict:
        resp = await self._client.patch(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def delete(self, path: str, **kwargs) -> dict:
        resp = await self._client.delete(path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()


api_client = BotClient()
