from datetime import date, datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.keyboards.event_list_keyboard import build_event_list_keyboard
from bot.keyboards.inline_calendar import build_calendar_keyboard, build_time_grid_keyboard
from bot.keyboards.recurrence_keyboard import build_recurrence_mode_keyboard
from bot.services.api_client import api_client
from bot.states.create_states import RescheduleStates

router = Router()


@router.message(Command("reschedule"))
@router.message(F.text == "Перенести")
async def cmd_reschedule(message: Message, state: FSMContext):
    today = date.today().isoformat()
    try:
        events = await api_client.get(
            "/api/v1/events/day",
            params={"telegram_user_id": message.from_user.id, "date": today},
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        return

    if not events:
        await message.answer("Нет событий для переноса.")
        return

    await state.set_state(RescheduleStates.choose_event)
    await message.answer(
        "Выберите встречу для переноса:",
        reply_markup=build_event_list_keyboard(events, action="reschedule"),
    )


@router.callback_query(F.data.startswith("event:reschedule:"), RescheduleStates.choose_event)
async def reschedule_event_selected(callback: CallbackQuery, state: FSMContext):
    event_id = callback.data.split(":", 2)[2]
    await state.update_data(event_id=event_id)

    # Check if recurring (simplified check - just ask)
    builder_text = (
        "Это повторяющееся событие. Что изменить?"
        if True  # simplified
        else "Выберите новую дату:"
    )
    await state.set_state(RescheduleStates.choose_recurrence_mode)
    await callback.message.edit_text(
        "Это повторяющееся событие. Что изменить?",
        reply_markup=build_recurrence_mode_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("recmode:"), RescheduleStates.choose_recurrence_mode)
async def reschedule_recurrence_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":")[1]
    if mode == "cancel":
        await state.clear()
        await callback.message.edit_text("Перенос отменён.")
        await callback.answer()
        return

    await state.update_data(recurrence_edit_mode=mode)
    today = date.today()
    await state.set_state(RescheduleStates.choose_date)
    await callback.message.edit_text(
        "Выберите новую дату:",
        reply_markup=build_calendar_keyboard(today.year, today.month),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:pick:"), RescheduleStates.choose_date)
async def reschedule_date_picked(callback: CallbackQuery, state: FSMContext):
    _, _, year, month, day = callback.data.split(":")
    chosen_date = date(int(year), int(month), int(day))
    await state.update_data(new_date=chosen_date.isoformat())
    await state.set_state(RescheduleStates.choose_time)
    await callback.message.edit_text(
        f"Дата: {chosen_date.strftime('%d.%m.%y')}\nВыберите новое время:",
        reply_markup=build_time_grid_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:nav:"), RescheduleStates.choose_date)
async def reschedule_calendar_nav(callback: CallbackQuery, state: FSMContext):
    _, _, year, month = callback.data.split(":")
    await callback.message.edit_reply_markup(
        reply_markup=build_calendar_keyboard(int(year), int(month))
    )
    await callback.answer()


@router.callback_query(F.data.startswith("time:pick:"), RescheduleStates.choose_time)
async def reschedule_time_picked(callback: CallbackQuery, state: FSMContext):
    _, _, hour, minute = callback.data.split(":")
    await state.update_data(new_time=f"{int(hour):02d}:{int(minute):02d}")
    data = await state.get_data()

    new_date = data.get("new_date")
    new_time = data.get("new_time")
    event_id = data.get("event_id")
    mode = data.get("recurrence_edit_mode", "single")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить", callback_data="reschedule:confirm")
    builder.button(text="Отмена", callback_data="reschedule:cancel")
    builder.adjust(2)

    await state.set_state(RescheduleStates.confirm)
    await callback.message.edit_text(
        f"Перенести на {new_date} {new_time}?",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "reschedule:confirm", RescheduleStates.confirm)
async def reschedule_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    event_id = data["event_id"]
    new_date = data["new_date"]
    new_time = data["new_time"]
    mode = data.get("recurrence_edit_mode", "single")

    new_start = datetime.strptime(f"{new_date}T{new_time}:00", "%Y-%m-%dT%H:%M:%S")
    new_end = new_start + timedelta(hours=1)

    try:
        await api_client.patch(
            f"/api/v1/events/{event_id}",
            json={
                "start_at": new_start.isoformat(),
                "end_at": new_end.isoformat(),
                "recurrence_edit_mode": mode,
            },
            params={"telegram_user_id": callback.from_user.id},
        )
        await callback.message.edit_text("Встреча перенесена!")
    except Exception as e:
        await callback.message.edit_text(f"Ошибка при переносе: {e}")

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "reschedule:cancel")
async def reschedule_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Перенос отменён.")
    await callback.answer()
