import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_async_session
from api.models.exchange_account import ExchangeAccount
from api.models.user import User
from api.schemas.account import AccountResponse, OAuthStartResponse
from api.services.auth.oauth import exchange_code, get_auth_url
from api.services.auth.oauth import refresh_token as refresh_oauth_token

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


async def get_or_create_user(telegram_user_id: int, session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(telegram_user_id=telegram_user_id)
        session.add(user)
        await session.flush()
    return user


@router.post("/oauth/start")
async def oauth_start(
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
) -> OAuthStartResponse:
    user = await get_or_create_user(telegram_user_id, session)
    auth_url, state = await get_auth_url(str(user.id))
    return OAuthStartResponse(auth_url=auth_url, state=state)


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        token_data = await exchange_code(code, state)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    user_id = uuid.UUID(token_data["user_id"])

    # Get user profile from Graph
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        profile = resp.json() if resp.status_code == 200 else {}

    # Check if account already exists
    email = profile.get("mail") or profile.get("userPrincipalName", "unknown@example.com")
    result = await session.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.user_id == user_id,
            ExchangeAccount.email == email,
        )
    )
    account = result.scalar_one_or_none()

    if account:
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data["refresh_token"]
        account.token_expires_at = token_data["token_expires_at"]
        account.status = "active"
        account.updated_at = datetime.now(timezone.utc)
    else:
        account = ExchangeAccount(
            user_id=user_id,
            tenant_id=profile.get("id"),
            email=email,
            display_name=profile.get("displayName"),
            token_expires_at=token_data["token_expires_at"],
            status="active",
        )
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data["refresh_token"]
        session.add(account)

    await session.flush()
    return {"message": "Account connected successfully", "email": email}


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    result = await session.execute(
        select(ExchangeAccount).where(ExchangeAccount.user_id == user.id)
    )
    return result.scalars().all()


@router.post("/{account_id}/refresh")
async def refresh_account(
    account_id: uuid.UUID,
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    result = await session.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.id == account_id,
            ExchangeAccount.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        new_tokens = await refresh_oauth_token(str(account.id), account.refresh_token)
        account.access_token = new_tokens["access_token"]
        account.refresh_token = new_tokens["refresh_token"]
        account.token_expires_at = new_tokens["token_expires_at"]
        account.status = "active"
        account.updated_at = datetime.now(timezone.utc)
    except Exception as e:
        account.status = "expired"
        account.updated_at = datetime.now(timezone.utc)
        raise HTTPException(status_code=400, detail=str(e))

    return {"message": "Token refreshed successfully"}


@router.delete("/{account_id}")
async def delete_account(
    account_id: uuid.UUID,
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    result = await session.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.id == account_id,
            ExchangeAccount.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    await session.delete(account)
    return {"message": "Account deleted"}
