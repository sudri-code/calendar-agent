import uuid
from datetime import datetime, timedelta, date
from typing import Optional

import structlog
from dateutil.rrule import rrulestr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event

logger = structlog.get_logger()

OCCURRENCES_CACHE_TTL = 1800  # 30 minutes


def get_week_start(dt: datetime) -> str:
    """Get ISO week start date string."""
    start = dt - timedelta(days=dt.weekday())
    return start.strftime("%Y-%m-%d")


async def get_virtual_occurrences(
    master: Event,
    start: datetime,
    end: datetime,
    redis_client=None,
) -> list[datetime]:
    """Get virtual occurrence datetimes for a recurring event series."""
    if not master.recurrence_rule:
        return []

    cache_key = f"occurrences:{master.id}:{get_week_start(start)}"

    if redis_client:
        cached = await redis_client.get(cache_key)
        if cached:
            import json
            return [datetime.fromisoformat(d) for d in json.loads(cached)]

    try:
        rule = rrulestr(master.recurrence_rule, dtstart=master.start_at)
        occurrences = list(rule.between(start, end, inc=True))
    except Exception as e:
        logger.error("Failed to compute occurrences", master_id=str(master.id), error=str(e))
        return []

    if redis_client:
        import json
        await redis_client.setex(
            cache_key,
            OCCURRENCES_CACHE_TTL,
            json.dumps([d.isoformat() for d in occurrences]),
        )

    return occurrences


async def get_exceptions_for_master(
    master_id: uuid.UUID,
    session: AsyncSession,
) -> list[Event]:
    """Get all exception rows for a recurring series master."""
    result = await session.execute(
        select(Event).where(
            Event.recurrence_master_id == master_id,
            Event.deleted_at.is_(None),
        )
    )
    return result.scalars().all()


async def invalidate_occurrences_cache(master_id: uuid.UUID, redis_client) -> None:
    """Invalidate all cached occurrences for a series master."""
    pattern = f"occurrences:{master_id}:*"
    keys = await redis_client.keys(pattern)
    if keys:
        await redis_client.delete(*keys)
