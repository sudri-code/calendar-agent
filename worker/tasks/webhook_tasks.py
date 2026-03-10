import asyncio
import structlog

from worker.celery_config import app

logger = structlog.get_logger()


@app.task(name="worker.tasks.webhook_tasks.process_graph_notification_task", bind=True, max_retries=3)
def process_graph_notification_task(self, notification: dict):
    """Process a Microsoft Graph change notification."""
    async def _run():
        resource = notification.get("resource", "")
        change_type = notification.get("changeType", "")
        subscription_id = notification.get("subscriptionId", "")

        logger.info(
            "Processing Graph notification",
            resource=resource,
            change_type=change_type,
        )

        from sqlalchemy import select
        from api.db.session import async_session_factory
        from api.models.event import Event
        from api.models.graph_subscription import GraphSubscription

        # Find the subscription to get account info
        async with async_session_factory() as session:
            sub_result = await session.execute(
                select(GraphSubscription).where(
                    GraphSubscription.external_subscription_id == subscription_id
                )
            )
            subscription = sub_result.scalar_one_or_none()

        if not subscription:
            logger.warning("Subscription not found", subscription_id=subscription_id)
            return

        # Extract event ID from resource path
        # e.g. "Users/{user-id}/Events/{event-id}"
        resource_parts = resource.split("/")
        if len(resource_parts) < 2:
            return

        external_event_id = resource_parts[-1]

        if change_type == "deleted":
            from api.services.events.event_service import handle_external_delete
            await handle_external_delete(external_event_id)
            return

        # For created/updated - find event in DB
        async with async_session_factory() as session:
            result = await session.execute(
                select(Event).where(
                    Event.external_event_id == external_event_id,
                    Event.deleted_at.is_(None),
                )
            )
            event = result.scalar_one_or_none()

        if not event:
            logger.debug("Event not found in DB, skipping", external_event_id=external_event_id)
            return

        from shared.constants import EventRole
        if event.role == EventRole.PRIMARY:
            from api.services.events.mirror_service import sync_mirror_to_primary
            await sync_mirror_to_primary(event.id)
        elif event.role == EventRole.MIRROR:
            from api.services.events.mirror_service import restore_mirror_from_primary
            await restore_mirror_from_primary(event.id)

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error("Webhook task failed", error=str(e))
        raise self.retry(exc=e, countdown=30)
