from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_async_session
from api.routers.accounts import get_or_create_user
from api.schemas.contact import ContactResponse, ContactSearchResult
from api.services.contact_sync import search_contacts, sync_contacts

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactResponse])
async def list_contacts_endpoint(
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    from sqlalchemy import select
    from api.models.contact import Contact

    user = await get_or_create_user(telegram_user_id, session)
    result = await session.execute(
        select(Contact).where(Contact.user_id == user.id).limit(100)
    )
    return result.scalars().all()


@router.get("/search", response_model=list[ContactSearchResult])
async def search_contacts_endpoint(
    telegram_user_id: int = Query(...),
    q: str = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    return await search_contacts(user.id, q)


@router.post("/sync")
async def sync_contacts_endpoint(
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    count = await sync_contacts(user.id)
    return {"message": f"Synced {count} contacts"}
