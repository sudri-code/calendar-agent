from datetime import date, datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers.today import _format_event
from bot.services.api_client import api_client

router = Router()


@router.message(Command("week"))
@router.message(F.text == "Моя неделя")
async def cmd_week(message: Message):
    today = date.today()
    # Start from Monday of current week
    monday = today - timedelta(days=today.weekday())
    date_from = monday.isoformat()

    try:
        events = await api_client.get(
            "/api/v1/events/week",
            params={"telegram_user_id": message.from_user.id, "date_from": date_from},
        )
    except Exception as e:
        await message.answer(f"Ошибка при загрузке событий: {e}")
        return

    if not events:
        await message.answer(f"На этой неделе (с {date_from}) событий нет.")
        return

    # Group by day
    by_day: dict[str, list] = {}
    for event in events:
        start_at = event.get("start_at", "")
        try:
            dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
            day_key = dt.strftime("%Y-%m-%d")
        except Exception:
            day_key = "unknown"
        by_day.setdefault(day_key, []).append(event)

    lines = [f"<b>События на неделю (с {date_from}):</b>"]
    for day_key in sorted(by_day.keys()):
        try:
            day_dt = datetime.strptime(day_key, "%Y-%m-%d")
            day_name = day_dt.strftime("%A, %d.%m")
        except Exception:
            day_name = day_key
        lines.append(f"\n<b>{day_name}:</b>")
        for event in by_day[day_key]:
            lines.append(_format_event(event))

    await message.answer("\n".join(lines), parse_mode="HTML")
