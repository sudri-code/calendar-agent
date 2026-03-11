from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.handlers.create import _process_llm_draft, _ask_calendar
from bot.handlers.today import _format_event
from bot.services.api_client import api_client
from bot.config import bot_settings
from bot.states.slot_states import SlotStates

router = Router()

KNOWN_BUTTON_TEXTS = frozenset({
    "Создать встречу", "Найти слот", "Мой день", "Моя неделя",
    "Перенести", "Удалить", "Аккаунты", "Календари", "Контакты", "Настройки",
})


@router.message(
    StateFilter(default_state),
    F.text,
    ~F.text.in_(KNOWN_BUTTON_TEXTS),
    ~F.text.startswith("/"),
)
async def handle_free_text(message: Message, state: FSMContext):
    await message.answer("Разбираю ваш запрос...")
    try:
        result = await api_client.post(
            "/api/v1/events/draft/parse",
            params={"text": message.text, "telegram_user_id": message.from_user.id},
        )
    except Exception as e:
        await message.answer(f"Ошибка при разборе: {e}")
        return

    intent = result.get("intent", "unknown")

    if intent == "create_event":
        await state.update_data(telegram_user_id=message.from_user.id, mode="text")
        await _process_llm_draft(message, state, message.text, result=result)

    elif intent == "reschedule_event":
        from bot.handlers.reschedule import cmd_reschedule
        await cmd_reschedule(message, state)

    elif intent == "delete_event":
        from bot.handlers.delete import cmd_delete
        await cmd_delete(message, state)

    elif intent == "find_slot":
        await _handle_find_slot(message, state, result)

    elif intent == "show_day":
        await _handle_show_day(message, result)

    elif intent == "show_week":
        await _handle_show_week(message, result)

    else:
        await message.answer(
            "Не понял запрос. Попробуйте:\n\n"
            "• «Встреча с Иваном завтра в 15:00 на час»\n"
            "• «Найди свободное время на этой неделе»\n"
            "• «Покажи мой день»\n"
            "• «Перенеси встречу»\n\n"
            "Или воспользуйтесь кнопками меню.",
        )


async def _handle_find_slot(message: Message, state: FSMContext, result: dict):
    raw = result.get("raw") or {}
    participants = raw.get("participants") or []
    date_range = raw.get("date_range") or {}
    duration = raw.get("duration_minutes")

    # Resolve participant names to emails via contacts
    attendees = []
    for p in participants:
        if p.get("email"):
            attendees.append(p["email"])
        elif p.get("name"):
            try:
                contacts = await api_client.get(
                    "/api/v1/contacts/search",
                    params={"telegram_user_id": message.from_user.id, "q": p["name"]},
                )
                if contacts and contacts[0].get("email"):
                    attendees.append(contacts[0]["email"])
            except Exception:
                pass

    date_from = date_range.get("from")
    date_to = date_range.get("to") or date_from
    await state.update_data(attendees=attendees)

    if date_from and date_to and duration:
        # All data available — call API and go straight to slot selection
        await message.answer("Ищу свободные слоты...")
        try:
            slots = await api_client.post(
                "/api/v1/events/find-slots",
                json={
                    "date_from": f"{date_from}T08:00:00",
                    "date_to": f"{date_to}T20:00:00",
                    "duration_minutes": int(duration),
                    "attendee_emails": attendees,
                },
                params={"telegram_user_id": message.from_user.id},
            )
        except Exception as e:
            await message.answer(f"Ошибка при поиске слотов: {e}")
            return

        await state.update_data(found_slots=slots, duration=int(duration))
        await state.set_state(SlotStates.review_options)

        tz = ZoneInfo(bot_settings.ews_timezone)
        builder = InlineKeyboardBuilder()
        for i, slot in enumerate(slots[:8]):
            try:
                start = datetime.fromisoformat(slot["start_at"].replace("Z", "+00:00"))
                start_local = start.astimezone(tz) if start.tzinfo else start
                label = start_local.strftime("%d.%m %H:%M")
            except Exception:
                label = f"Слот {i + 1}"
            builder.button(text=label, callback_data=f"slot:pick:{i}")
        builder.adjust(2)
        await message.answer("Выберите подходящий слот:", reply_markup=builder.as_markup())

    elif date_from and date_to:
        # Have dates but no duration
        await state.update_data(
            date_from=f"{date_from}T08:00:00",
            date_to=f"{date_to}T20:00:00",
        )
        await state.set_state(SlotStates.enter_duration)
        from bot.handlers.find_slot import build_duration_keyboard
        await message.answer("Выберите длительность встречи:", reply_markup=build_duration_keyboard())

    else:
        # Missing date range — ask for it
        today_d = date.today()
        next_week = today_d + timedelta(days=7)
        await state.set_state(SlotStates.enter_range)
        await message.answer(
            f"Введите диапазон дат в формате ДД.ММ:ДД.ММ\n"
            f"Например: {today_d.strftime('%d.%m')}:{next_week.strftime('%d.%m')}"
        )


async def _handle_show_day(message: Message, result: dict):
    raw = result.get("raw") or {}
    date_range = raw.get("date_range") or {}
    target = date_range.get("from") or date.today().isoformat()
    try:
        events = await api_client.get(
            "/api/v1/events/day",
            params={"telegram_user_id": message.from_user.id, "date": target},
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        return
    date_fmt = date.fromisoformat(target).strftime("%d.%m.%Y")
    if not events:
        await message.answer(f"На {date_fmt} событий нет.")
        return
    lines = [f"<b>События на {date_fmt}:</b>\n"]
    for e in events:
        lines.append(_format_event(e))
    await message.answer("\n\n".join(lines), parse_mode="HTML")


async def _handle_show_week(message: Message, result: dict):
    raw = result.get("raw") or {}
    date_range = raw.get("date_range") or {}
    today_d = date.today()
    if date_range.get("from"):
        try:
            d = date.fromisoformat(date_range["from"])
            monday = d - timedelta(days=d.weekday())
        except Exception:
            monday = today_d - timedelta(days=today_d.weekday())
    else:
        monday = today_d - timedelta(days=today_d.weekday())
    try:
        events = await api_client.get(
            "/api/v1/events/week",
            params={"telegram_user_id": message.from_user.id, "date_from": monday.isoformat()},
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        return
    if not events:
        await message.answer("На этой неделе событий нет.")
        return

    tz = ZoneInfo(bot_settings.ews_timezone)
    by_day: dict = defaultdict(list)
    for ev in events:
        start_str = ev.get("start_at", "")
        try:
            dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            dt_local = dt.astimezone(tz) if dt.tzinfo else dt
            day_key = dt_local.strftime("%A, %d.%m")
        except Exception:
            day_key = start_str[:10]
        by_day[day_key].append(ev)

    lines = []
    for day, evs in by_day.items():
        lines.append(f"<b>{day}</b>")
        for ev in evs:
            lines.append(_format_event(ev))
    await message.answer("\n\n".join(lines), parse_mode="HTML")
