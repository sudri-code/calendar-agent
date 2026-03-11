import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from api.db.session import get_async_session
from api.models.calendar import Calendar
from api.models.user import User
from api.routers.accounts import get_or_create_user
from api.schemas.calendar import CalendarPatch, CalendarResponse
from api.services.calendar_sync import sync_calendars

router = APIRouter(prefix="/api/v1/calendars", tags=["calendars"])


@router.get("", response_model=list[CalendarResponse])
async def list_calendars_endpoint(
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    excluded_names = {"дни рождения", "birthdays", "birthday"}
    result = await session.execute(
        select(Calendar)
        .options(joinedload(Calendar.account))
        .where(Calendar.user_id == user.id)
    )
    cals = [c for c in result.scalars().all() if c.name.strip().lower() not in excluded_names]
    return [CalendarResponse.from_calendar(c) for c in cals]


@router.patch("/{calendar_id}", response_model=CalendarResponse)
async def patch_calendar(
    calendar_id: uuid.UUID,
    patch: CalendarPatch,
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    result = await session.execute(
        select(Calendar).where(
            Calendar.id == calendar_id,
            Calendar.user_id == user.id,
        )
    )
    cal = result.scalar_one_or_none()
    if not cal:
        raise HTTPException(status_code=404, detail="Calendar not found")

    if patch.is_active is not None:
        cal.is_active = patch.is_active
    if patch.is_mirror_enabled is not None:
        cal.is_mirror_enabled = patch.is_mirror_enabled
    cal.updated_at = datetime.now(timezone.utc)

    return cal


@router.post("/sync")
async def sync_calendars_endpoint(
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    synced = await sync_calendars(user.id)
    return {"message": f"Synced {len(synced)} calendars"}
