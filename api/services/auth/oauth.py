import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import redis.asyncio as aioredis

from api.config import settings
from api.exceptions import AuthExpiredError


MS_AUTH_BASE = "https://login.microsoftonline.com"
MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

OAUTH_STATE_TTL = 600  # 10 minutes


def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def get_auth_url(user_id: str, state_token: str | None = None) -> str:
    """Generate Microsoft OAuth authorization URL with CSRF state stored in Redis."""
    redis = _get_redis()

    if state_token is None:
        state_token = secrets.token_urlsafe(32)

    state_key = f"oauth_state:{state_token}"
    await redis.set(state_key, user_id, ex=OAUTH_STATE_TTL)
    await redis.aclose()

    params = {
        "client_id": settings.ms_client_id,
        "response_type": "code",
        "redirect_uri": settings.ms_redirect_uri,
        "scope": " ".join(settings.ms_scopes_list),
        "state": state_token,
        "response_mode": "query",
    }

    auth_url = f"{MS_AUTH_BASE}/{settings.ms_tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"
    return auth_url, state_token


async def exchange_code(code: str, state: str) -> dict:
    """Exchange OAuth code for tokens after validating CSRF state."""
    redis = _get_redis()

    state_key = f"oauth_state:{state}"
    user_id = await redis.get(state_key)

    if not user_id:
        await redis.aclose()
        raise AuthExpiredError("Invalid or expired OAuth state")

    await redis.delete(state_key)
    await redis.aclose()

    token_url = f"{MS_AUTH_BASE}/{settings.ms_tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": settings.ms_client_id,
        "client_secret": settings.ms_client_secret,
        "code": code,
        "redirect_uri": settings.ms_redirect_uri,
        "grant_type": "authorization_code",
        "scope": " ".join(settings.ms_scopes_list),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()
        token_data = resp.json()

    return {
        "user_id": user_id,
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_in": token_data.get("expires_in", 3600),
        "token_expires_at": datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600)),
    }


async def refresh_token(account_id: str, refresh_tok: str) -> dict:
    """Refresh an access token using the refresh token."""
    from api.utils.redis_lock import redis_lock

    async with redis_lock(f"token_refresh:{account_id}", timeout=30):
        token_url = f"{MS_AUTH_BASE}/{settings.ms_tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": settings.ms_client_id,
            "client_secret": settings.ms_client_secret,
            "refresh_token": refresh_tok,
            "grant_type": "refresh_token",
            "scope": " ".join(settings.ms_scopes_list),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data=data)
            if resp.status_code in (400, 401):
                raise AuthExpiredError("Refresh token is invalid or expired")
            resp.raise_for_status()
            token_data = resp.json()

        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", refresh_tok),
            "expires_in": token_data.get("expires_in", 3600),
            "token_expires_at": datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600)),
        }
