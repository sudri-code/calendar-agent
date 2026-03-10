from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.recurrence_keyboard import (
    build_days_keyboard,
    build_recurrence_end_type_keyboard,
)
from bot.states.create_states import CreateEventStates

router = Router()


@router.callback_query(F.data == "rec:custom", CreateEventStates.choose_recurrence)
async def recurrence_custom(callback: CallbackQuery, state: FSMContext):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for label, code in [("Ежедневно", "daily"), ("Еженедельно", "weekly"),
                        ("Ежемесячно", "monthly"), ("Ежегодно", "yearly")]:
        builder.button(text=label, callback_data=f"recfreq:{code}")
    builder.adjust(2)
    await state.set_state(CreateEventStates.recurrence_frequency)
    await callback.message.edit_text("Частота повторения:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("recfreq:"), CreateEventStates.recurrence_frequency)
async def recurrence_freq_selected(callback: CallbackQuery, state: FSMContext):
    freq = callback.data.split(":")[1]
    await state.update_data(rec_frequency=freq)

    if freq == "weekly":
        # Ask which days
        await state.set_state(CreateEventStates.recurrence_days)
        await callback.message.edit_text(
            "Выберите дни недели:",
            reply_markup=build_days_keyboard([]),
        )
    else:
        await state.set_state(CreateEventStates.recurrence_end_type)
        await callback.message.edit_text(
            "Когда заканчивается повторение?",
            reply_markup=build_recurrence_end_type_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("day:"), CreateEventStates.recurrence_days)
async def day_toggle(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("rec_days", []))
    code = callback.data.split(":")[1]

    if code == "done":
        await state.set_state(CreateEventStates.recurrence_end_type)
        await callback.message.edit_text(
            "Когда заканчивается повторение?",
            reply_markup=build_recurrence_end_type_keyboard(),
        )
    else:
        if code in selected:
            selected.discard(code)
        else:
            selected.add(code)
        await state.update_data(rec_days=list(selected))
        await callback.message.edit_reply_markup(
            reply_markup=build_days_keyboard(list(selected))
        )
    await callback.answer()


@router.callback_query(F.data.startswith("recend:"), CreateEventStates.recurrence_end_type)
async def recurrence_end_type(callback: CallbackQuery, state: FSMContext):
    end_type = callback.data.split(":")[1]
    await state.update_data(rec_end_type=end_type)

    if end_type == "no_end":
        await _finalize_recurrence(callback, state)
    elif end_type == "by_date":
        await state.set_state(CreateEventStates.recurrence_end_date)
        await callback.message.edit_text("Введите дату окончания (ГГГГ-ММ-ДД):")
    elif end_type == "by_count":
        await state.set_state(CreateEventStates.recurrence_count)
        await callback.message.edit_text("Введите количество повторений:")
    await callback.answer()


@router.message(CreateEventStates.recurrence_end_date, F.text)
async def recurrence_end_date(message: Message, state: FSMContext):
    await state.update_data(rec_end_date=message.text)
    await _finalize_recurrence_message(message, state)


@router.message(CreateEventStates.recurrence_count, F.text)
async def recurrence_count(message: Message, state: FSMContext):
    try:
        count = int(message.text)
        await state.update_data(rec_count=count)
    except ValueError:
        await message.answer("Введите число.")
        return
    await _finalize_recurrence_message(message, state)


async def _finalize_recurrence(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    recurrence = {
        "frequency": data.get("rec_frequency", "daily"),
        "interval": 1,
        "days_of_week": data.get("rec_days"),
        "end_type": data.get("rec_end_type", "no_end"),
        "end_date": data.get("rec_end_date"),
        "count": data.get("rec_count"),
    }
    await state.update_data(recurrence=recurrence)
    from bot.handlers.create import _show_confirm
    await _show_confirm(callback.message, state)


async def _finalize_recurrence_message(message: Message, state: FSMContext):
    data = await state.get_data()
    recurrence = {
        "frequency": data.get("rec_frequency", "daily"),
        "interval": 1,
        "days_of_week": data.get("rec_days"),
        "end_type": data.get("rec_end_type", "no_end"),
        "end_date": data.get("rec_end_date"),
        "count": data.get("rec_count"),
    }
    await state.update_data(recurrence=recurrence)
    from bot.handlers.create import _show_confirm
    await _show_confirm(message, state)
