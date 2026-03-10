import asyncio
import structlog

from worker.celery_config import app

logger = structlog.get_logger()


@app.task(name="worker.tasks.reconciliation_tasks.reconcile_sync_groups_task")
def reconcile_sync_groups_task():
    """Daily reconciliation of sync groups - compare primary vs mirrors."""
    async def _run():
        from sqlalchemy import select
        from worker.db import make_session_factory
        async_session_factory = make_session_factory()
        from api.models.sync_group import SyncGroup
        from api.services.events.mirror_service import repair_sync_group
        from shared.constants import SyncGroupState

        async with async_session_factory() as session:
            result = await session.execute(
                select(SyncGroup).where(
                    SyncGroup.state.in_([SyncGroupState.ACTIVE, SyncGroupState.DEGRADED])
                ).limit(100)
            )
            groups = result.scalars().all()

        logger.info("Starting reconciliation", group_count=len(groups))

        for group in groups:
            try:
                await repair_sync_group(group.id)
                logger.debug("Sync group repaired", group_id=str(group.id))
            except Exception as e:
                logger.error(
                    "Failed to reconcile sync group",
                    group_id=str(group.id),
                    error=str(e),
                )

        logger.info("Reconciliation complete")

    asyncio.run(_run())
