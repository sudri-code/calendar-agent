import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog

from api.config import settings
from api.exceptions import AuthExpiredError, ExternalRateLimitError, InsufficientPermissionsError

logger = structlog.get_logger()

MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphClient:
    """Microsoft Graph API client with auto-refresh and rate limiting."""

    def __init__(self, account):
        self.account = account
        self._http = httpx.AsyncClient(timeout=30.0)

    async def _get_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        from datetime import timedelta
        from api.services.auth.oauth import refresh_token as refresh_oauth_token
        from api.db.session import async_session_factory
        from api.models.exchange_account import ExchangeAccount
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        expires_at = self.account.token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Proactive refresh 5 minutes before expiry
        if expires_at - now < timedelta(minutes=5):
            new_tokens = await refresh_oauth_token(
                str(self.account.id), self.account.refresh_token
            )
            async with async_session_factory() as session:
                result = await session.execute(
                    select(ExchangeAccount).where(ExchangeAccount.id == self.account.id)
                )
                acc = result.scalar_one_or_none()
                if acc:
                    acc.access_token = new_tokens["access_token"]
                    acc.refresh_token = new_tokens["refresh_token"]
                    acc.token_expires_at = new_tokens["token_expires_at"]
                    await session.commit()
                    self.account = acc

        return self.account.access_token

    async def _request(
        self,
        method: str,
        path: str,
        retry_count: int = 0,
        **kwargs,
    ) -> Any:
        """Make a Graph API request with retry logic."""
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            **kwargs.pop("headers", {}),
        }

        url = f"{MS_GRAPH_BASE}{path}"

        try:
            response = await self._http.request(method, url, headers=headers, **kwargs)
        except httpx.RequestError as e:
            logger.error("Graph API request error", error=str(e), path=path)
            raise

        if response.status_code == 401:
            if retry_count < 1:
                # Try refreshing token once
                from api.services.auth.oauth import refresh_token as refresh_oauth_token
                new_tokens = await refresh_oauth_token(
                    str(self.account.id), self.account.refresh_token
                )
                self.account.access_token_encrypted = __import__('api.utils.encryption', fromlist=['encrypt']).encrypt(new_tokens["access_token"])
                return await self._request(method, path, retry_count=retry_count + 1, **kwargs)
            raise AuthExpiredError(f"Graph API 401 for account {self.account.email}")

        if response.status_code == 403:
            raise InsufficientPermissionsError(
                f"Insufficient permissions for {path}"
            )

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            if retry_count < 3:
                logger.warning("Graph API rate limit hit, waiting", retry_after=retry_after)
                await asyncio.sleep(min(retry_after, 60))
                return await self._request(method, path, retry_count=retry_count + 1, **kwargs)
            raise ExternalRateLimitError("Graph API rate limit exceeded", retry_after=retry_after)

        if response.status_code == 204:
            return None

        response.raise_for_status()

        if response.content:
            return response.json()
        return None

    async def get(self, path: str, **kwargs) -> Any:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> Any:
        return await self._request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> Any:
        return await self._request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> Any:
        return await self._request("DELETE", path, **kwargs)

    async def close(self):
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
