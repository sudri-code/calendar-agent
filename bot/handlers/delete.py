from datetime import date
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.event_list_keyboard import build_event_list_keyboard
from bot.keyboards.recurrence_keyboard import build_recurrence_mode_keyboard
from bot.services.api_client import api_client
from bot.states.create_states import DeleteStates

router = Router()


@router.message(Command("delete"))
@router.message(F.text == "Удалить")
async def cmd_delete(message: Message, state: FSMContext):
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
        await message.answer("Нет событий для удаления.")
        return

    await state.set_state(DeleteStates.choose_event)
    await message.answer(
        "Выберите встречу для удаления:",
        reply_markup=build_event_list_keyboard(events, action="delete"),
    )


@router.callback_query(F.data.startswith("event:delete:"), DeleteStates.choose_event)
async def delete_event_selected(callback: CallbackQuery, state: FSMContext):
    event_id = callback.data.split(":", 2)[2]
    await state.update_data(event_id=event_id)
    await state.set_state(DeleteStates.choose_recurrence_mode)
    await callback.message.edit_text(
        "Это повторяющееся событие. Что удалить?",
        reply_markup=build_recurrence_mode_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("recmode:"), DeleteStates.choose_recurrence_mode)
async def delete_recurrence_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":")[1]
    if mode == "cancel":
        await state.clear()
        await callback.message.edit_text("Удаление отменено.")
        await callback.answer()
        return

    await state.update_data(recurrence_delete_mode=mode)

    builder = InlineKeyboardBuilder()
    builder.button(text="Удалить", callback_data="delete:confirm")
    builder.button(text="Отмена", callback_data="delete:cancel")
    builder.adjust(2)

    await state.set_state(DeleteStates.confirm)
    await callback.message.edit_text(
        "Вы уверены, что хотите удалить встречу?",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "delete:confirm", DeleteStates.confirm)
async def delete_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    event_id = data["event_id"]
    mode = data.get("recurrence_delete_mode", "single")

    try:
        await api_client.delete(
            f"/api/v1/events/{event_id}",
            params={
                "telegram_user_id": callback.from_user.id,
                "recurrence_delete_mode": mode,
            },
        )
        await callback.message.edit_text("Встреча удалена!")
    except Exception as e:
        await callback.message.edit_text(f"Ошибка при удалении: {e}")

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "delete:cancel")
async def delete_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Удаление отменено.")
    await callback.answer()
