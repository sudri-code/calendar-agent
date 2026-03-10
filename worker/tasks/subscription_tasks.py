"""
On-premises Exchange does not use Graph API subscriptions.
Change detection is done via periodic EWS polling instead.
"""
import asyncio
import structlog

from worker.celery_config import app

logger = structlog.get_logger()


@app.task(name="worker.tasks.subscription_tasks.poll_calendar_changes_task")
def poll_calendar_changes_task():
    """
    Poll all active Exchange accounts for calendar changes.
    Compares current EWS events against DB state and syncs mirrors.
    Runs every 5 minutes via Celery Beat.
    """
    async def _run():
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select
        from api.db.session import async_session_factory
        from api.models.exchange_account import ExchangeAccount
        from api.models.calendar import Calendar
        from api.models.event import Event
        from api.services.ews.events import list_events
        from api.services.events.mirror_service import sync_mirror_to_primary
        from shared.constants import EventRole

        window_start = datetime.now(timezone.utc) - timedelta(days=1)
        window_end = datetime.now(timezone.utc) + timedelta(days=30)

        async with async_session_factory() as session:
            result = await session.execute(
                select(ExchangeAccount).where(ExchangeAccount.status == "active")
            )
            accounts = result.scalars().all()

        for account in accounts:
            try:
                async with async_session_factory() as session:
                    cal_result = await session.execute(
                        select(Calendar).where(
                            Calendar.account_id == account.id,
                            Calendar.is_active == True,
                        )
                    )
                    calendars = cal_result.scalars().all()

                for calendar in calendars:
                    ews_events = await list_events(
                        account,
                        calendar.external_calendar_id,
                        window_start,
                        window_end,
                    )
                    ews_ids = {e["id"] for e in ews_events if e.get("id")}

                    async with async_session_factory() as session:
                        db_result = await session.execute(
                            select(Event).where(
                                Event.calendar_id == calendar.id,
                                Event.role == EventRole.PRIMARY,
                                Event.deleted_at.is_(None),
                                Event.start_at >= window_start,
                            )
                        )
                        db_events = db_result.scalars().all()

                    for db_event in db_events:
                        if db_event.external_event_id not in ews_ids:
                            # Event deleted in Exchange
                            logger.info(
                                "Detected external delete",
                                event_id=str(db_event.id),
                                external_id=db_event.external_event_id,
                            )
                            from api.services.events.event_service import handle_external_delete
                            await handle_external_delete(db_event.external_event_id)
                        else:
                            # Check for updates by comparing changeKey
                            ews_ev = next(
                                (e for e in ews_events if e["id"] == db_event.external_event_id),
                                None,
                            )
                            if ews_ev and ews_ev.get("changeKey") != db_event.last_seen_change_key:
                                logger.info(
                                    "Detected external update, syncing mirrors",
                                    event_id=str(db_event.id),
                                )
                                await sync_mirror_to_primary(db_event.id)
                                async with async_session_factory() as session:
                                    ev = await session.get(Event, db_event.id)
                                    if ev:
                                        ev.last_seen_change_key = ews_ev.get("changeKey")
                                        await session.commit()

            except Exception as e:
                logger.error(
                    "Polling failed for account",
                    account_email=account.email,
                    error=str(e),
                )

    asyncio.run(_run())
