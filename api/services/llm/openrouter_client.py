import httpx
import structlog
from typing import Any, Optional

from api.config import settings

logger = structlog.get_logger()

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://calendar-agent.app",
                "X-Title": "Calendar Agent",
            },
            timeout=60.0,
        )

    async def chat_completion(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        response_format: Optional[dict] = None,
    ) -> dict:
        model = model or settings.openrouter_model
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if response_format:
            payload["response_format"] = response_format

        logger.debug("OpenRouter request", model=model, url=str(self._client.base_url) + "/chat/completions")
        response = await self._client.post("/chat/completions", json=payload)
        if not response.is_success:
            logger.error("OpenRouter error", status=response.status_code, model=model, body=response.text[:500])
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
