import uuid
from datetime import datetime, timezone, date
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import async_session_factory
from api.exceptions import (
    EventNotFoundError, MirrorSyncError, SyncGroupNotFoundError,
    CalendarConflictError
)
from api.models.calendar import Calendar
from api.models.event import Event
from api.models.exchange_account import ExchangeAccount
from api.models.sync_group import SyncGroup
from api.services.events.mirror_service import build_mirror_body, sync_mirror_to_primary
from api.services.graph.events import (
    create_event as graph_create_event,
    delete_event as graph_delete_event,
    update_event as graph_update_event,
)
from api.utils.redis_lock import redis_lock
from shared.constants import EventRole, SyncGroupState
from shared.schemas.event import EventDraft, EventPatch

logger = structlog.get_logger()


async def _get_account_for_calendar(session: AsyncSession, calendar: Calendar) -> ExchangeAccount:
    result = await session.execute(
        select(ExchangeAccount).where(ExchangeAccount.id == calendar.account_id)
    )
    return result.scalar_one()


def _build_graph_event_body(draft: EventDraft) -> dict:
    """Convert EventDraft to Graph API event body."""
    body = {
        "subject": draft.title,
        "body": {
            "contentType": "text",
            "content": draft.description or "",
        },
        "start": {
            "dateTime": draft.start_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": draft.timezone,
        },
        "end": {
            "dateTime": draft.end_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": draft.timezone,
        },
        "attendees": [
            {
                "emailAddress": {
                    "address": a.email,
                    "name": a.name or a.email,
                },
                "type": "required",
            }
            for a in (draft.attendees or [])
        ],
    }

    if draft.recurrence:
        from api.services.events.recurrence_mapper import rrule_to_graph_recurrence
        from shared.schemas.event import RecurrenceConfig

        rec = draft.recurrence
        # Build rrule string from config
        freq_map = {
            "daily": "DAILY",
            "weekly": "WEEKLY",
            "monthly": "MONTHLY",
            "yearly": "YEARLY",
        }
        rrule_parts = [f"FREQ={freq_map.get(rec.frequency, 'DAILY')}"]
        if rec.interval > 1:
            rrule_parts.append(f"INTERVAL={rec.interval}")
        if rec.days_of_week:
            day_map = {"MO": "MO", "TU": "TU", "WE": "WE", "TH": "TH", "FR": "FR", "SA": "SA", "SU": "SU"}
            byday = ",".join(day_map.get(d.upper(), d.upper()) for d in rec.days_of_week)
            rrule_parts.append(f"BYDAY={byday}")
        if rec.end_type == "by_date" and rec.end_date:
            until = rec.end_date.replace("-", "") + "T235959Z"
            rrule_parts.append(f"UNTIL={until}")
        elif rec.end_type == "by_count" and rec.count:
            rrule_parts.append(f"COUNT={rec.count}")

        rrule_str = "RRULE:" + ";".join(rrule_parts)
        graph_rec = rrule_to_graph_recurrence(rrule_str, draft.start_at.date())
        body["recurrence"] = graph_rec

    return body


async def create_event(
    user_id: uuid.UUID,
    draft: EventDraft,
    session: AsyncSession,
) -> Event:
    """Create primary event and all mirror events."""
    # Get target calendar
    result = await session.execute(
        select(Calendar).where(
            Calendar.id == uuid.UUID(str(draft.calendar_id)),
            Calendar.user_id == user_id,
            Calendar.is_active == True,
        )
    )
    primary_calendar = result.scalar_one_or_none()
    if not primary_calendar:
        raise ValueError(f"Calendar {draft.calendar_id} not found or inactive")

    primary_account = await _get_account_for_calendar(session, primary_calendar)

    async with redis_lock(f"sync_group:{user_id}"):
        # Create sync group
        sync_group = SyncGroup(user_id=user_id, state=SyncGroupState.ACTIVE)
        session.add(sync_group)
        await session.flush()

        # Create primary in Graph
        graph_body = _build_graph_event_body(draft)
        graph_event = await graph_create_event(
            primary_account,
            primary_calendar.external_calendar_id,
            graph_body,
        )

        # Save primary event in DB
        is_recurring = draft.recurrence is not None
        rrule_str = None
        if is_recurring and draft.recurrence:
            from api.services.events.recurrence_mapper import rrule_to_graph_recurrence
            rec = draft.recurrence
            freq_map = {"daily": "DAILY", "weekly": "WEEKLY", "monthly": "MONTHLY", "yearly": "YEARLY"}
            rrule_parts = [f"FREQ={freq_map.get(rec.frequency, 'DAILY')}"]
            if rec.interval > 1:
                rrule_parts.append(f"INTERVAL={rec.interval}")
            if rec.days_of_week:
                byday = ",".join(d.upper() for d in rec.days_of_week)
                rrule_parts.append(f"BYDAY={byday}")
            if rec.end_type == "by_date" and rec.end_date:
                until = rec.end_date.replace("-", "") + "T235959Z"
                rrule_parts.append(f"UNTIL={until}")
            elif rec.end_type == "by_count" and rec.count:
                rrule_parts.append(f"COUNT={rec.count}")
            rrule_str = "RRULE:" + ";".join(rrule_parts)

        primary_event = Event(
            user_id=user_id,
            calendar_id=primary_calendar.id,
            external_event_id=graph_event["id"],
            sync_group_id=sync_group.id,
            role=EventRole.PRIMARY,
            status="active",
            title=draft.title,
            description=draft.description,
            start_at=draft.start_at,
            end_at=draft.end_at,
            timezone=draft.timezone,
            attendees_json=[a.model_dump() for a in (draft.attendees or [])],
            recurrence_rule=rrule_str,
            recurrence_json=graph_event.get("recurrence"),
            is_recurrence_master=is_recurring,
        )
        session.add(primary_event)
        await session.flush()

        # Update sync group with primary event id
        sync_group.primary_event_id = primary_event.id
        await session.flush()

        # Get all mirror calendars (active + mirror_enabled, excluding primary)
        mirrors_result = await session.execute(
            select(Calendar).where(
                Calendar.user_id == user_id,
                Calendar.is_active == True,
                Calendar.is_mirror_enabled == True,
                Calendar.id != primary_calendar.id,
            )
        )
        mirror_calendars = mirrors_result.scalars().all()

        failed_mirrors = []
        for mirror_cal in mirror_calendars:
            mirror_account = await _get_account_for_calendar(session, mirror_cal)
            mirror_graph_body = build_mirror_body(primary_event, primary_calendar.name)
            if is_recurring and "recurrence" in graph_body:
                mirror_graph_body["recurrence"] = graph_body["recurrence"]

            try:
                mirror_graph_event = await graph_create_event(
                    mirror_account,
                    mirror_cal.external_calendar_id,
                    mirror_graph_body,
                )
                mirror_event = Event(
                    user_id=user_id,
                    calendar_id=mirror_cal.id,
                    external_event_id=mirror_graph_event["id"],
                    sync_group_id=sync_group.id,
                    role=EventRole.MIRROR,
                    status="active",
                    title=f"[Занято] {draft.title}",
                    description=mirror_graph_body["body"]["content"],
                    start_at=draft.start_at,
                    end_at=draft.end_at,
                    timezone=draft.timezone,
                    attendees_json=[],
                    source_event_id=primary_event.id,
                    recurrence_rule=rrule_str,
                    is_recurrence_master=is_recurring,
                )
                session.add(mirror_event)
            except Exception as e:
                logger.error(
                    "Failed to create mirror event",
                    calendar_id=str(mirror_cal.id),
                    error=str(e),
                )
                failed_mirrors.append(str(mirror_cal.id))

        if failed_mirrors:
            sync_group.state = SyncGroupState.DEGRADED

        await session.commit()

        if failed_mirrors:
            raise MirrorSyncError(
                "Event created but some mirrors failed",
                failed_calendars=failed_mirrors,
            )

        return primary_event


async def delete_event(
    user_id: uuid.UUID,
    event_id: uuid.UUID,
    recurrence_delete_mode: str = "single",
    session: Optional[AsyncSession] = None,
) -> None:
    """Delete event and all related mirrors."""
    should_close = session is None
    if session is None:
        session_ctx = async_session_factory()
        session = await session_ctx.__aenter__()

    try:
        result = await session.execute(
            select(Event).where(
                Event.id == event_id,
                Event.user_id == user_id,
            )
        )
        event = result.scalar_one_or_none()
        if not event:
            raise EventNotFoundError(f"Event {event_id} not found")

        cal_result = await session.execute(
            select(Calendar).where(Calendar.id == event.calendar_id)
        )
        calendar = cal_result.scalar_one()
        account = await _get_account_for_calendar(session, calendar)

        if recurrence_delete_mode == "all" or not event.is_recurrence_master:
            # Delete from Graph
            try:
                await graph_delete_event(
                    account,
                    calendar.external_calendar_id,
                    event.external_event_id,
                )
            except Exception as e:
                logger.warning("Failed to delete from Graph", error=str(e))

            # Mark as deleted in DB
            now = datetime.now(timezone.utc)
            event.deleted_at = now

            # Find and delete all mirrors
            mirrors_result = await session.execute(
                select(Event).where(
                    Event.sync_group_id == event.sync_group_id,
                    Event.role == EventRole.MIRROR,
                    Event.deleted_at.is_(None),
                )
            )
            mirrors = mirrors_result.scalars().all()

            for mirror in mirrors:
                mirror_cal_result = await session.execute(
                    select(Calendar).where(Calendar.id == mirror.calendar_id)
                )
                mirror_cal = mirror_cal_result.scalar_one_or_none()
                if mirror_cal:
                    mirror_acc = await _get_account_for_calendar(session, mirror_cal)
                    try:
                        await graph_delete_event(
                            mirror_acc,
                            mirror_cal.external_calendar_id,
                            mirror.external_event_id,
                        )
                    except Exception as e:
                        logger.warning("Failed to delete mirror from Graph", error=str(e))
                mirror.deleted_at = now

            # Mark sync group deleted
            sg_result = await session.execute(
                select(SyncGroup).where(SyncGroup.id == event.sync_group_id)
            )
            sg = sg_result.scalar_one_or_none()
            if sg:
                sg.state = SyncGroupState.DELETED
                sg.updated_at = now

        await session.commit()

    finally:
        if should_close:
            await session_ctx.__aexit__(None, None, None)


async def handle_external_delete(external_event_id: str) -> None:
    """Handle external deletion of an event detected via webhook."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Event).where(
                Event.external_event_id == external_event_id,
                Event.deleted_at.is_(None),
            )
        )
        event = result.scalar_one_or_none()
        if not event:
            return

        if event.role == EventRole.PRIMARY:
            await delete_event(
                event.user_id,
                event.id,
                recurrence_delete_mode="all",
                session=session,
            )
        else:
            # Mirror was deleted externally - restore it
            await restore_mirror_from_primary_by_external_id(event.id)


async def restore_mirror_from_primary_by_external_id(mirror_id: uuid.UUID) -> None:
    """Restore a mirror that was deleted externally."""
    from api.services.events.mirror_service import sync_mirror_to_primary

    async with async_session_factory() as session:
        result = await session.execute(
            select(Event).where(Event.id == mirror_id)
        )
        mirror = result.scalar_one_or_none()
        if not mirror:
            return

        primary_result = await session.execute(
            select(Event).where(
                Event.sync_group_id == mirror.sync_group_id,
                Event.role == EventRole.PRIMARY,
                Event.deleted_at.is_(None),
            )
        )
        primary = primary_result.scalar_one_or_none()
        if primary:
            await sync_mirror_to_primary(primary.id)
