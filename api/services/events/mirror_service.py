import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import async_session_factory
from api.exceptions import MirrorSyncError
from api.models.calendar import Calendar
from api.models.event import Event
from api.models.exchange_account import ExchangeAccount
from api.models.sync_group import SyncGroup
from api.services.graph.events import create_event, delete_event, update_event
from shared.constants import EventRole, SyncGroupState

logger = structlog.get_logger()


def build_mirror_body(primary: Event, primary_calendar_name: str) -> dict:
    """Build the Graph event body for a mirror event."""
    attendees_str = ", ".join(
        a.get("emailAddress", {}).get("address", "") or a.get("email", "")
        for a in (primary.attendees_json or [])
    ) or "нет участников"

    return {
        "subject": f"[Занято] {primary.title}",
        "body": {
            "contentType": "text",
            "content": (
                f"Зеркальная блокировка. Основная встреча: «{primary.title}» "
                f"в календаре «{primary_calendar_name}». "
                f"Участники: {attendees_str}. "
                f"Sync group: {primary.sync_group_id}."
            ),
        },
        "start": {
            "dateTime": primary.start_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": primary.timezone,
        },
        "end": {
            "dateTime": primary.end_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": primary.timezone,
        },
        "showAs": "busy",
        "isReminderOn": False,
        "attendees": [],
    }


async def sync_mirror_to_primary(primary_event_id: uuid.UUID) -> None:
    """Update all mirror events to match the primary event."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Event).where(Event.id == primary_event_id)
        )
        primary = result.scalar_one_or_none()
        if not primary:
            logger.warning("Primary event not found", event_id=str(primary_event_id))
            return

        # Get primary calendar info
        cal_result = await session.execute(
            select(Calendar).where(Calendar.id == primary.calendar_id)
        )
        primary_calendar = cal_result.scalar_one_or_none()
        primary_calendar_name = primary_calendar.name if primary_calendar else "Unknown"

        # Get all mirror events in this sync group
        mirrors_result = await session.execute(
            select(Event).where(
                Event.sync_group_id == primary.sync_group_id,
                Event.role == EventRole.MIRROR,
                Event.deleted_at.is_(None),
            )
        )
        mirrors = mirrors_result.scalars().all()

        failed_calendars = []
        mirror_body = build_mirror_body(primary, primary_calendar_name)

        for mirror in mirrors:
            cal_result = await session.execute(
                select(Calendar).where(Calendar.id == mirror.calendar_id)
            )
            mirror_calendar = cal_result.scalar_one_or_none()
            if not mirror_calendar:
                continue

            acc_result = await session.execute(
                select(ExchangeAccount).where(ExchangeAccount.id == mirror_calendar.account_id)
            )
            account = acc_result.scalar_one_or_none()
            if not account:
                continue

            try:
                await update_event(
                    account,
                    mirror_calendar.external_calendar_id,
                    mirror.external_event_id,
                    mirror_body,
                )
                mirror.title = f"[Занято] {primary.title}"
                mirror.start_at = primary.start_at
                mirror.end_at = primary.end_at
                mirror.updated_at = datetime.now(timezone.utc)
                logger.info("Mirror synced", mirror_id=str(mirror.id))
            except Exception as e:
                logger.error("Failed to sync mirror", mirror_id=str(mirror.id), error=str(e))
                failed_calendars.append(str(mirror_calendar.id))

        if failed_calendars:
            # Mark sync group as degraded
            sg_result = await session.execute(
                select(SyncGroup).where(SyncGroup.id == primary.sync_group_id)
            )
            sg = sg_result.scalar_one_or_none()
            if sg:
                sg.state = SyncGroupState.DEGRADED
                sg.updated_at = datetime.now(timezone.utc)

        await session.commit()

        if failed_calendars:
            raise MirrorSyncError(
                f"Failed to sync {len(failed_calendars)} mirrors",
                failed_calendars=failed_calendars,
            )


async def restore_mirror_from_primary(mirror_event_id: uuid.UUID) -> None:
    """Restore a mirror event from its primary (overwrite manual changes)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Event).where(Event.id == mirror_event_id)
        )
        mirror = result.scalar_one_or_none()
        if not mirror:
            return

        # Find primary in same sync group
        primary_result = await session.execute(
            select(Event).where(
                Event.sync_group_id == mirror.sync_group_id,
                Event.role == EventRole.PRIMARY,
                Event.deleted_at.is_(None),
            )
        )
        primary = primary_result.scalar_one_or_none()
        if not primary:
            return

    await sync_mirror_to_primary(primary.id)


async def repair_sync_group(sync_group_id: uuid.UUID) -> None:
    """Compare primary vs mirrors and restore consistency."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Event).where(
                Event.sync_group_id == sync_group_id,
                Event.role == EventRole.PRIMARY,
                Event.deleted_at.is_(None),
            )
        )
        primary = result.scalar_one_or_none()
        if not primary:
            return

    await sync_mirror_to_primary(primary.id)
