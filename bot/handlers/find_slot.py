from datetime import date, datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import api_client
from bot.states.slot_states import SlotStates

router = Router()

DURATION_OPTIONS = [
    ("30 мин", 30), ("1 час", 60), ("1.5 ч", 90), ("2 часа", 120),
]


def build_duration_keyboard():
    builder = InlineKeyboardBuilder()
    for label, minutes in DURATION_OPTIONS:
        builder.button(text=label, callback_data=f"slotdur:{minutes}")
    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("find_slot"))
@router.message(F.text == "Найти слот")
async def cmd_find_slot(message: Message, state: FSMContext):
    await state.set_state(SlotStates.enter_people)
    await message.answer(
        "Введите email или имена участников (через запятую).\n"
        "Или нажмите /skip для поиска только по своим календарям:"
    )


@router.message(SlotStates.enter_people, F.text)
async def slot_people_entered(message: Message, state: FSMContext):
    if message.text == "/skip":
        attendees = []
    else:
        parts = [p.strip() for p in message.text.split(",") if p.strip()]
        attendees = []
        for part in parts:
            if "@" in part:
                attendees.append(part)
            else:
                try:
                    contacts = await api_client.get(
                        "/api/v1/contacts/search",
                        params={"telegram_user_id": message.from_user.id, "q": part},
                    )
                    if contacts and contacts[0].get("email"):
                        attendees.append(contacts[0]["email"])
                except Exception:
                    pass

    await state.update_data(attendees=attendees)
    await state.set_state(SlotStates.enter_range)
    today = date.today()
    next_week = today + timedelta(days=7)
    await message.answer(
        f"Введите диапазон дат в формате ГГГГ-ММ-ДД:ГГГГ-ММ-ДД\n"
        f"Или нажмите /skip для диапазона: {today} – {next_week}"
    )


@router.message(SlotStates.enter_range, F.text)
async def slot_range_entered(message: Message, state: FSMContext):
    if message.text == "/skip":
        today = date.today()
        date_from = today.isoformat()
        date_to = (today + timedelta(days=7)).isoformat()
    else:
        parts = message.text.split(":")
        if len(parts) != 2:
            await message.answer("Неверный формат. Используйте ГГГГ-ММ-ДД:ГГГГ-ММ-ДД")
            return
        date_from, date_to = parts[0].strip(), parts[1].strip()

    await state.update_data(date_from=date_from, date_to=date_to)
    await state.set_state(SlotStates.enter_duration)
    await message.answer("Выберите длительность:", reply_markup=build_duration_keyboard())


@router.callback_query(F.data.startswith("slotdur:"), SlotStates.enter_duration)
async def slot_duration_picked(callback: CallbackQuery, state: FSMContext):
    duration = int(callback.data.split(":")[1])
    await state.update_data(duration=duration)
    data = await state.get_data()

    await callback.message.edit_text("Ищу свободные слоты...")

    try:
        slots = await api_client.post(
            "/api/v1/events/find-slots",
            json={
                "date_from": f"{data['date_from']}T08:00:00",
                "date_to": f"{data['date_to']}T20:00:00",
                "duration_minutes": duration,
                "attendee_emails": data.get("attendees", []),
            },
            params={"telegram_user_id": callback.from_user.id},
        )
    except Exception as e:
        await callback.message.edit_text(f"Ошибка при поиске слотов: {e}")
        await state.clear()
        await callback.answer()
        return

    if not slots:
        await callback.message.edit_text("Свободных слотов не найдено.")
        await state.clear()
        await callback.answer()
        return

    await state.update_data(found_slots=slots)
    await state.set_state(SlotStates.review_options)

    builder = InlineKeyboardBuilder()
    for i, slot in enumerate(slots[:8]):
        try:
            start = datetime.fromisoformat(slot["start_at"])
            label = start.strftime("%d.%m %H:%M")
        except Exception:
            label = f"Слот {i + 1}"
        builder.button(text=label, callback_data=f"slot:pick:{i}")
    builder.adjust(2)

    await callback.message.edit_text(
        "Выберите подходящий слот:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("slot:pick:"), SlotStates.review_options)
async def slot_picked(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[2])
    data = await state.get_data()
    slots = data.get("found_slots", [])

    if idx >= len(slots):
        await callback.message.edit_text("Слот не найден.")
        await state.clear()
        await callback.answer()
        return

    chosen_slot = slots[idx]
    await state.update_data(chosen_slot=chosen_slot)

    try:
        start = datetime.fromisoformat(chosen_slot["start_at"])
        end = datetime.fromisoformat(chosen_slot["end_at"])
    except Exception:
        await callback.message.edit_text("Ошибка при выборе слота.")
        await state.clear()
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="Создать встречу", callback_data="slot:create")
    builder.button(text="Отмена", callback_data="slot:cancel")
    builder.adjust(2)

    await state.set_state(SlotStates.confirm_create)
    await callback.message.edit_text(
        f"Слот: {start.strftime('%d.%m.%Y %H:%M')} – {end.strftime('%H:%M')}\n"
        "Создать встречу в этот слот?",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "slot:create", SlotStates.confirm_create)
async def slot_create(callback: CallbackQuery, state: FSMContext):
    # Transition to create flow with prefilled data
    from bot.states.create_states import CreateEventStates
    data = await state.get_data()
    chosen_slot = data.get("chosen_slot", {})

    try:
        start = datetime.fromisoformat(chosen_slot["start_at"])
        end = datetime.fromisoformat(chosen_slot["end_at"])
    except Exception:
        await state.clear()
        await callback.answer()
        return

    await state.set_state(CreateEventStates.choose_calendar)
    await state.update_data(
        mode="step",
        chosen_date=start.strftime("%Y-%m-%d"),
        chosen_time=start.strftime("%H:%M"),
        duration=int((end - start).total_seconds() / 60),
        attendees=data.get("attendees", []),
        draft=None,
    )

    try:
        calendars = await api_client.get(
            "/api/v1/calendars",
            params={"telegram_user_id": callback.from_user.id},
        )
        active_cals = [c for c in calendars if c.get("is_active")]
    except Exception:
        active_cals = []

    if not active_cals:
        await callback.message.edit_text("Нет активных календарей.")
        await state.clear()
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for cal in active_cals[:10]:
        builder.button(text=cal["name"], callback_data=f"cal_select:{cal['id']}")
    builder.adjust(1)

    await callback.message.edit_text(
        "Выберите основной календарь:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "slot:cancel")
async def slot_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Поиск слота отменён.")
    await callback.answer()
