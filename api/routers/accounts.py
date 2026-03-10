import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_async_session
from api.models.exchange_account import ExchangeAccount
from api.models.user import User
from api.schemas.account import AccountResponse, AddAccountRequest

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


async def get_or_create_user(telegram_user_id: int, session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(telegram_user_id=telegram_user_id)
        session.add(user)
        await session.flush()
    return user


@router.post("", response_model=AccountResponse, status_code=201)
async def add_account(
    request: AddAccountRequest,
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    """Add an on-premises Exchange account by verifying EWS credentials."""
    user = await get_or_create_user(telegram_user_id, session)

    # Verify credentials by attempting to connect
    from api.services.ews.client import EWSClient

    class _TempAccount:
        email = request.email
        ews_server = request.ews_server
        username_encrypted = ""
        password_encrypted = ""
        auth_type = request.auth_type

        @property
        def username(self):
            return request.username

        @property
        def password(self):
            return request.password

    try:
        client = EWSClient(_TempAccount())
        await client.get_calendars()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot connect to Exchange: {e}")

    # Upsert account
    result = await session.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.user_id == user.id,
            ExchangeAccount.email == request.email,
        )
    )
    account = result.scalar_one_or_none()

    if account:
        account.ews_server = request.ews_server
        account.domain = request.domain
        account.username = request.username
        account.password = request.password
        account.auth_type = request.auth_type
        account.display_name = request.display_name
        account.status = "active"
        account.updated_at = datetime.now(timezone.utc)
    else:
        account = ExchangeAccount(
            user_id=user.id,
            email=request.email,
            display_name=request.display_name,
            ews_server=request.ews_server,
            domain=request.domain,
            auth_type=request.auth_type,
            status="active",
        )
        account.username = request.username
        account.password = request.password
        session.add(account)

    await session.flush()
    return account


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


@router.post("/{account_id}/verify")
async def verify_account(
    account_id: uuid.UUID,
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    """Re-verify EWS credentials (e.g. after password change)."""
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

    from api.services.ews.client import EWSClient
    try:
        client = EWSClient(account)
        await client.get_calendars()
        account.status = "active"
        account.updated_at = datetime.now(timezone.utc)
        return {"message": "Credentials verified", "status": "active"}
    except Exception as e:
        account.status = "error"
        account.updated_at = datetime.now(timezone.utc)
        raise HTTPException(status_code=400, detail=f"Verification failed: {e}")


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
