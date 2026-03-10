import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_async_session
from api.exceptions import (
    CalendarConflictError, EventNotFoundError, MirrorSyncError
)
from api.models.calendar import Calendar
from api.routers.accounts import get_or_create_user
from api.schemas.event import (
    AvailabilityRequest, CreateEventRequest, EventResponse,
    FindSlotsRequest, UpdateEventRequest,
)
from api.services.availability.availability_service import check_slot
from api.services.availability.slot_finder import find_slots
from api.services.events.event_service import create_event, delete_event
from api.services.ews.events import list_events

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["events"])


async def _fetch_ews_events(
    user_id: uuid.UUID, start: datetime, end: datetime, session: AsyncSession
) -> list[dict]:
    """Fetch events directly from EWS for all active user calendars."""
    result = await session.execute(
        select(Calendar)
        .options(joinedload(Calendar.account))
        .where(Calendar.user_id == user_id, Calendar.is_active == True)
    )
    calendars = result.scalars().all()

    events: list[dict] = []
    for cal in calendars:
        try:
            ews_events = await list_events(cal.account, cal.external_calendar_id, start, end)
            for e in ews_events:
                events.append({
                    "title": e.get("subject") or "Без названия",
                    "start_at": e.get("start") or "",
                    "end_at": e.get("end") or "",
                    "attendees_json": [],
                    "recurrence_rule": None,
                    "calendar_name": cal.name,
                })
        except Exception as e:
            logger.warning("Failed to fetch EWS events", calendar=cal.name, error=str(e))

    events.sort(key=lambda x: x["start_at"])
    return events


@router.get("/day")
async def get_day_events(
    telegram_user_id: int = Query(...),
    date: str = Query(...),  # YYYY-MM-DD
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    day_end = day.replace(hour=23, minute=59, second=59)
    return await _fetch_ews_events(user.id, day, day_end, session)


@router.get("/week")
async def get_week_events(
    telegram_user_id: int = Query(...),
    date_from: str = Query(...),  # YYYY-MM-DD
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    return await _fetch_ews_events(user.id, start, end, session)


@router.post("/draft/parse")
async def parse_event_draft(
    text: str = Query(...),
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    from api.services.llm.parser import parse_event_text
    from datetime import date
    today = date.today()
    draft = await parse_event_text(text, user_id=user.id, today=today)
    return draft


@router.post("/check-availability")
async def check_availability(
    request: AvailabilityRequest,
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    result = await check_slot(
        user.id,
        request.start_at,
        request.end_at,
        request.attendee_emails,
    )
    return result


@router.post("", response_model=EventResponse)
async def create_event_endpoint(
    request: CreateEventRequest,
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    try:
        event = await create_event(user.id, request, session)
        return event
    except MirrorSyncError as e:
        raise HTTPException(
            status_code=207,
            detail={"message": str(e), "failed_calendars": e.failed_calendars},
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{event_id}")
async def delete_event_endpoint(
    event_id: uuid.UUID,
    telegram_user_id: int = Query(...),
    recurrence_delete_mode: str = Query(default="single"),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    try:
        await delete_event(user.id, event_id, recurrence_delete_mode, session)
        return {"message": "Event deleted"}
    except EventNotFoundError:
        raise HTTPException(status_code=404, detail="Event not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/find-slots")
async def find_slots_endpoint(
    request: FindSlotsRequest,
    telegram_user_id: int = Query(...),
    session: AsyncSession = Depends(get_async_session),
):
    user = await get_or_create_user(telegram_user_id, session)
    slots = await find_slots(
        user.id,
        request.date_from,
        request.date_to,
        request.duration_minutes,
        request.attendee_emails,
        request.preferred_time_from,
        request.preferred_time_to,
    )
    return slots
