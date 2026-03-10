import asyncio
from datetime import datetime, timedelta, timezone

import structlog

from worker.celery_config import app

logger = structlog.get_logger()


@app.task(name="worker.tasks.subscription_tasks.renew_expiring_subscriptions_task")
def renew_expiring_subscriptions_task():
    """Renew Graph subscriptions expiring within 2 days."""
    async def _run():
        from sqlalchemy import select
        from api.db.session import async_session_factory
        from api.models.graph_subscription import GraphSubscription
        from api.models.exchange_account import ExchangeAccount
        from api.services.graph.client import GraphClient

        threshold = datetime.now(timezone.utc) + timedelta(days=2)

        async with async_session_factory() as session:
            result = await session.execute(
                select(GraphSubscription).where(
                    GraphSubscription.expires_at < threshold,
                    GraphSubscription.status == "active",
                )
            )
            expiring = result.scalars().all()

        for sub in expiring:
            async with async_session_factory() as session:
                acc_result = await session.execute(
                    select(ExchangeAccount).where(
                        ExchangeAccount.id == sub.account_id
                    )
                )
                account = acc_result.scalar_one_or_none()
                if not account:
                    continue

                try:
                    new_expiry = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
                    async with GraphClient(account) as client:
                        await client.patch(
                            f"/subscriptions/{sub.external_subscription_id}",
                            json={"expirationDateTime": new_expiry},
                        )

                    sub.expires_at = datetime.now(timezone.utc) + timedelta(days=3)
                    sub.updated_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.info("Subscription renewed", sub_id=sub.external_subscription_id)

                except Exception as e:
                    logger.error(
                        "Failed to renew subscription, recreating",
                        sub_id=str(sub.id),
                        error=str(e),
                    )
                    try:
                        await _recreate_subscription(sub, account, session)
                    except Exception as recreate_e:
                        logger.error("Failed to recreate subscription", error=str(recreate_e))
                        sub.status = "error"
                        sub.updated_at = datetime.now(timezone.utc)
                        await session.commit()

    asyncio.run(_run())


async def _recreate_subscription(sub, account, session) -> None:
    """Recreate a failed subscription."""
    from api.config import settings
    from api.services.graph.client import GraphClient
    from datetime import datetime, timedelta, timezone

    new_expiry = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

    body = {
        "changeType": "created,updated,deleted",
        "notificationUrl": f"{settings.api_base_url}/api/v1/webhooks/graph",
        "resource": sub.resource,
        "expirationDateTime": new_expiry,
        "clientState": settings.internal_api_key,
    }

    async with GraphClient(account) as client:
        new_sub = await client.post("/subscriptions", json=body)

    sub.external_subscription_id = new_sub["id"]
    sub.expires_at = datetime.now(timezone.utc) + timedelta(days=3)
    sub.status = "active"
    sub.updated_at = datetime.now(timezone.utc)
    await session.commit()


@app.task(name="worker.tasks.subscription_tasks.create_subscription_task")
def create_subscription_task(user_id: str, account_id: str):
    """Create a new Graph subscription for an account."""
    async def _run():
        from sqlalchemy import select
        from api.config import settings
        from api.db.session import async_session_factory
        from api.models.exchange_account import ExchangeAccount
        from api.models.graph_subscription import GraphSubscription
        from api.services.graph.client import GraphClient
        import uuid
        from datetime import datetime, timedelta, timezone

        async with async_session_factory() as session:
            acc_result = await session.execute(
                select(ExchangeAccount).where(ExchangeAccount.id == uuid.UUID(account_id))
            )
            account = acc_result.scalar_one_or_none()
            if not account:
                return

            expiry = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
            body = {
                "changeType": "created,updated,deleted",
                "notificationUrl": f"{settings.api_base_url}/api/v1/webhooks/graph",
                "resource": "me/events",
                "expirationDateTime": expiry,
                "clientState": settings.internal_api_key,
            }

            async with GraphClient(account) as client:
                graph_sub = await client.post("/subscriptions", json=body)

            subscription = GraphSubscription(
                user_id=uuid.UUID(user_id),
                account_id=uuid.UUID(account_id),
                resource="me/events",
                external_subscription_id=graph_sub["id"],
                expires_at=datetime.now(timezone.utc) + timedelta(days=3),
                status="active",
            )
            session.add(subscription)
            await session.commit()
            logger.info("Subscription created", account_id=account_id)

    asyncio.run(_run())
