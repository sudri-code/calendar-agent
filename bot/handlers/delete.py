from datetime import date, datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.handlers.today import _format_event
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

    await state.update_data(events_cache={e["id"] if isinstance(e, dict) else str(e): e for e in events} if isinstance(events, list) else {})
    await state.set_state(DeleteStates.choose_event)
    await message.answer(
        "Выберите встречу для удаления:",
        reply_markup=build_event_list_keyboard(events, action="delete"),
    )


@router.callback_query(F.data.startswith("event:delete:"), DeleteStates.choose_event)
async def delete_event_selected(callback: CallbackQuery, state: FSMContext):
    event_id = callback.data.split(":", 2)[2]
    data = await state.get_data()
    events_cache = data.get("events_cache", {})
    event_data = events_cache.get(event_id, {})
    is_recurring = event_data.get("isRecurring", False)

    await state.update_data(event_id=event_id)

    if is_recurring:
        await state.set_state(DeleteStates.choose_recurrence_mode)
        await callback.message.edit_text(
            "Это повторяющееся событие. Что удалить?",
            reply_markup=build_recurrence_mode_keyboard(),
        )
    else:
        await state.update_data(recurrence_delete_mode="single")
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


async def handle_free_slot_intent(message: Message, state: FSMContext, result: dict):
    """Handle 'free_slot' intent: show overlapping events and offer to delete them."""
    # Primary: use already-parsed draft (most reliable)
    draft = result.get("draft")
    slot_start = slot_end = None
    if draft and draft.get("start_at"):
        try:
            slot_start = datetime.fromisoformat(draft["start_at"])
            slot_end = datetime.fromisoformat(draft["end_at"])
        except Exception:
            pass

    # Fallback: parse from raw LLM fields
    if not slot_start:
        raw = result.get("raw") or {}
        date_range = raw.get("date_range") or {}
        start_time = raw.get("start_time")
        duration = raw.get("duration_minutes") or 60
        date_str = date_range.get("from")
        if not date_str or not start_time:
            await message.answer("Не смог определить дату или время. Попробуйте уточнить.")
            return
        try:
            slot_start = datetime.fromisoformat(f"{date_str}T{start_time}:00")
            slot_end = slot_start + timedelta(minutes=int(duration))
        except Exception:
            await message.answer("Не смог разобрать время. Попробуйте уточнить.")
            return

    date_str = slot_start.strftime("%Y-%m-%d")

    try:
        events = await api_client.get(
            "/api/v1/events/day",
            params={"telegram_user_id": message.from_user.id, "date": date_str},
        )
    except Exception as e:
        await message.answer(f"Ошибка при получении событий: {e}")
        return

    def _parse_naive(s: str) -> datetime | None:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except Exception:
            return None

    overlapping = []
    for ev in (events or []):
        ev_start = _parse_naive(ev.get("start_at", ""))
        ev_end = _parse_naive(ev.get("end_at", ""))
        if ev_start and ev_end and ev_start < slot_end and ev_end > slot_start:
            overlapping.append(ev)

    if not overlapping:
        await message.answer(
            f"В {slot_start.strftime('%H:%M')}–{slot_end.strftime('%H:%M')} нет встреч."
        )
        return

    lines = [
        f"<b>Встречи в {slot_start.strftime('%H:%M')}–{slot_end.strftime('%H:%M')}:</b>\n"
    ]
    for ev in overlapping:
        lines.append(_format_event(ev))

    n = len(overlapping)
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"Удалить {'все ' + str(n) + ' встречи' if n > 1 else 'встречу'}",
        callback_data="freeslot:confirm",
    )
    builder.button(text="Отмена", callback_data="freeslot:cancel")
    builder.adjust(1)

    # Collect ALL Exchange IDs for each overlapping event (including mirror copies)
    all_ids: list[str] = []
    for ev in overlapping:
        all_ids.extend(ev.get("_all_ids") or [ev["id"]])

    await state.update_data(free_slot_event_ids=all_ids)
    await state.set_state(DeleteStates.free_slot_confirm)
    await message.answer(
        "\n\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "freeslot:confirm", DeleteStates.free_slot_confirm)
async def freeslot_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    event_ids = data.get("free_slot_event_ids", [])
    await state.clear()

    await callback.message.edit_text("Удаляю встречи...")
    try:
        result = await api_client.post(
            "/api/v1/events/delete-by-exchange-ids",
            json=event_ids,
            params={"telegram_user_id": callback.from_user.id},
        )
        deleted = result.get("deleted", 0)
        errors = result.get("errors", [])
    except Exception as e:
        await callback.message.edit_text(f"Ошибка при удалении: {e}")
        await callback.answer()
        return

    if errors:
        await callback.message.edit_text(
            f"Удалено {deleted} из {len(event_ids)}.\nОшибки: {'; '.join(errors)}"
        )
    else:
        await callback.message.edit_text(
            f"✅ Слот освобождён, удалено встреч: {deleted}"
        )
    await callback.answer()


@router.callback_query(F.data == "freeslot:cancel", DeleteStates.free_slot_confirm)
async def freeslot_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()
