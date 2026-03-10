import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

import redis.asyncio as aioredis

from api.config import settings
from shared.schemas.webhook import GraphNotificationPayload

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@router.get("/graph", response_class=PlainTextResponse)
async def graph_webhook_validation(
    validationToken: str = Query(...),
) -> str:
    """Respond to Microsoft Graph webhook validation handshake."""
    return validationToken


@router.post("/graph", status_code=202)
async def graph_webhook_notification(
    request: Request,
    clientState: str = Query(default=None),
):
    """Handle incoming Microsoft Graph change notifications."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    notifications = body.get("value", [])
    redis = _get_redis()

    for notification in notifications:
        sub_id = notification.get("subscriptionId", "")
        client_state = notification.get("clientState", "")
        seq_num = notification.get("sequenceNumber")

        # Idempotency check using Redis
        if seq_num is not None:
            idempotency_key = f"webhook:processed:{sub_id}:{seq_num}"
            already_processed = await redis.exists(idempotency_key)
            if already_processed:
                logger.debug("Duplicate webhook notification skipped", seq_num=seq_num)
                continue
            await redis.setex(idempotency_key, 3600, "1")  # TTL=1h

        # Dispatch to Celery worker
        try:
            from worker.tasks.webhook_tasks import process_graph_notification_task
            process_graph_notification_task.delay(notification)
        except Exception as e:
            logger.error("Failed to dispatch webhook task", error=str(e))

    await redis.aclose()
    return {"status": "accepted"}
