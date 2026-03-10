import asyncio
import uuid

import structlog

from worker.celery_config import app

logger = structlog.get_logger()


@app.task(name="worker.tasks.sync_tasks.sync_calendars_task", bind=True, max_retries=3)
def sync_calendars_task(self, user_id: str):
    """Sync calendars for a user."""
    async def _run():
        from api.services.calendar_sync import sync_calendars
        await sync_calendars(uuid.UUID(user_id))

    try:
        asyncio.run(_run())
        logger.info("Calendars synced", user_id=user_id)
    except Exception as e:
        logger.error("Failed to sync calendars", user_id=user_id, error=str(e))
        raise self.retry(exc=e, countdown=60)


@app.task(name="worker.tasks.sync_tasks.sync_contacts_task", bind=True, max_retries=3)
def sync_contacts_task(self, user_id: str):
    """Sync contacts for a user."""
    async def _run():
        from api.services.contact_sync import sync_contacts
        await sync_contacts(uuid.UUID(user_id))

    try:
        asyncio.run(_run())
        logger.info("Contacts synced", user_id=user_id)
    except Exception as e:
        logger.error("Failed to sync contacts", user_id=user_id, error=str(e))
        raise self.retry(exc=e, countdown=60)


@app.task(name="worker.tasks.sync_tasks.sync_all_contacts_task")
def sync_all_contacts_task():
    """Sync contacts for all active users."""
    async def _run():
        from sqlalchemy import select
        from worker.db import make_session_factory
        async_session_factory = make_session_factory()
        from api.models.user import User
        from api.services.contact_sync import sync_contacts
        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.is_active == True)
            )
            users = result.scalars().all()

        for user in users:
            try:
                await sync_contacts(user.id)
            except Exception as e:
                logger.error("Failed to sync contacts for user", user_id=str(user.id), error=str(e))

    asyncio.run(_run())


@app.task(name="worker.tasks.sync_tasks.sync_all_calendars_task")
def sync_all_calendars_task():
    """Sync calendar list for all active users."""
    async def _run():
        from sqlalchemy import select
        from worker.db import make_session_factory
        async_session_factory = make_session_factory()
        from api.models.user import User
        from api.services.calendar_sync import sync_calendars

        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.is_active == True)
            )
            users = result.scalars().all()

        for user in users:
            try:
                await sync_calendars(user.id)
            except Exception as e:
                logger.error("Failed to sync calendars for user", user_id=str(user.id), error=str(e))

    asyncio.run(_run())
