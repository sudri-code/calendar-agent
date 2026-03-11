from datetime import datetime, timezone as stdlib_utc
from zoneinfo import ZoneInfo

from api.config import settings
from api.services.ews.client import EWSClient


def _to_ews_datetime(dt: datetime):
    """
    Convert Python datetime to exchangelib EWSDateTime.

    Если datetime наивный (без tzinfo), считаем, что он уже в локальной
    тайм-зоне пользователя (settings.ews_timezone), а не в UTC.
    """
    from exchangelib import EWSDateTime, UTC

    if dt.tzinfo is None:
        local_tz = ZoneInfo(settings.ews_timezone)
        dt = dt.replace(tzinfo=local_tz)

    # Конвертируем в UTC через stdlib, чтобы не получить EWSDateTime.
    # exchangelib.UTC — это EWSTimeZone; .astimezone(EWSTimeZone) вернёт EWSDateTime,
    # а EWSDateTime.from_datetime() запрещает принимать EWSDateTime на вход.
    dt_utc = dt.astimezone(stdlib_utc.utc)
    return EWSDateTime.from_datetime(dt_utc).replace(tzinfo=UTC)


async def list_events(account, calendar_id: str, start: datetime, end: datetime) -> list[dict]:
    async with EWSClient(account) as client:
        return await client.get_events(
            calendar_id,
            _to_ews_datetime(start),
            _to_ews_datetime(end),
            settings.ews_timezone,
        )


async def create_event(account, calendar_id: str, event_body: dict) -> dict:
    """
    event_body keys:
      subject, body, start (datetime), end (datetime),
      attendees: [{"email": ..., "name": ...}],
      recurrence: exchangelib Recurrence object or None
    """
    data = dict(event_body)
    if isinstance(data.get("start"), datetime):
        data["start"] = _to_ews_datetime(data["start"])
    if isinstance(data.get("end"), datetime):
        data["end"] = _to_ews_datetime(data["end"])

    async with EWSClient(account) as client:
        return await client.create_event(calendar_id, data)


async def update_event(account, calendar_id: str, item_id: str, patch_body: dict) -> dict:
    data = dict(patch_body)
    if isinstance(data.get("start"), datetime):
        data["start"] = _to_ews_datetime(data["start"])
    if isinstance(data.get("end"), datetime):
        data["end"] = _to_ews_datetime(data["end"])

    async with EWSClient(account) as client:
        return await client.update_event(item_id, "", data)


async def delete_event(account, calendar_id: str, item_id: str) -> None:
    async with EWSClient(account) as client:
        await client.delete_event(item_id)


async def get_event(account, calendar_id: str, item_id: str) -> dict:
    events = await list_events(account, calendar_id,
                               datetime(2000, 1, 1), datetime(2100, 1, 1))
    for e in events:
        if e.get("id") == item_id:
            return e
    raise ValueError(f"Event {item_id} not found")
