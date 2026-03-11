from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.api_client import api_client
from bot.config import bot_settings

router = Router()

RECURRENCE_LABELS = {
    "DAILY": "ежедневно",
    "WEEKLY": "еженедельно",
    "MONTHLY": "ежемесячно",
    "YEARLY": "ежегодно",
}

WEEKDAYS_RU = {
    "MO": "понедельникам", "TU": "вторникам", "WE": "средам",
    "TH": "четвергам", "FR": "пятницам", "SA": "субботам", "SU": "воскресеньям",
}


def _format_recurrence(rrule: str) -> str:
    """Format RRULE into human-readable Russian text."""
    if not rrule:
        return ""
    rrule = rrule.replace("RRULE:", "")
    props = {}
    for part in rrule.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            props[k] = v

    freq = props.get("FREQ", "")
    byday = props.get("BYDAY", "")

    if freq == "WEEKLY" and byday:
        days = [WEEKDAYS_RU.get(d.strip(), d) for d in byday.split(",")]
        return f"еженедельно по {', '.join(days)}"
    elif freq == "DAILY":
        interval = props.get("INTERVAL", "1")
        if interval == "1":
            return "ежедневно"
        return f"каждые {interval} дня"
    elif freq == "WEEKLY":
        return "еженедельно"
    elif freq == "MONTHLY":
        return "ежемесячно"
    elif freq == "YEARLY":
        return "ежегодно"
    return RECURRENCE_LABELS.get(freq, "")


def _format_event(event: dict) -> str:
    """Format event for display."""
    title = event.get("title", "Без названия")
    start_at = event.get("start_at", "")
    end_at = event.get("end_at", "")

    try:
        tz = ZoneInfo(bot_settings.ews_timezone)
        # Нормализуем ISO-строку и считаем, что сервер отдаёт время в UTC
        start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start_local = start.astimezone(tz)
        end_local = end.astimezone(tz)
        time_str = f"{start_local.strftime('%H:%M')} – {end_local.strftime('%H:%M')}"
    except Exception:
        time_str = ""

    attendees = event.get("attendees_json", [])
    attendee_str = ""
    if attendees:
        names = [a.get("name") or a.get("email", "") for a in attendees[:3]]
        attendee_str = f"\nУчастники: {', '.join(names)}"
        if len(attendees) > 3:
            attendee_str += f" +{len(attendees) - 3}"

    recurrence = event.get("recurrence_rule", "")
    rec_str = ""
    if recurrence:
        rec_label = _format_recurrence(recurrence)
        if rec_label:
            rec_str = f"\n🔁 Повторяется {rec_label}"

    return f"📅 <b>{title}</b>\n{time_str}{attendee_str}{rec_str}"


@router.message(Command("today"))
@router.message(F.text == "Мой день")
async def cmd_today(message: Message):
    today = date.today()
    try:
        events = await api_client.get(
            "/api/v1/events/day",
            params={"telegram_user_id": message.from_user.id, "date": today.isoformat()},
        )
    except Exception as e:
        await message.answer(f"Ошибка при загрузке событий: {e}")
        return

    today_fmt = today.strftime("%d.%m.%y")
    if not events:
        await message.answer(f"На сегодня ({today_fmt}) событий нет.")
        return

    lines = [f"<b>События на {today_fmt}:</b>\n"]
    for event in events:
        lines.append(_format_event(event))

    await message.answer("\n\n".join(lines), parse_mode="HTML")
