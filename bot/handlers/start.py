from aiogram import Router, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import any_state
from aiogram.types import Message

from bot.keyboards.main_menu import get_main_menu
from bot.services.api_client import api_client

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    # Register user via API (get_or_create)
    try:
        await api_client.get(
            "/api/v1/accounts",
            params={"telegram_user_id": message.from_user.id},
        )
    except Exception:
        pass

    await message.answer(
        f"Привет, {message.from_user.first_name}!\n\n"
        "Я помогу управлять вашими Exchange-календарями.\n\n"
        "Используйте кнопки меню или команды:\n"
        "/today — события на сегодня\n"
        "/week — события на неделю\n"
        "/create — создать встречу\n"
        "/find_slot — найти свободный слот\n"
        "/accounts — управление аккаунтами\n"
        "/settings — настройки",
        reply_markup=get_main_menu(),
    )


@router.message(Command("cancel"), StateFilter(any_state))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("Действие отменено.", reply_markup=get_main_menu())
    else:
        await message.answer("Нет активного действия.", reply_markup=get_main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Доступные команды:\n\n"
        "/start — главное меню\n"
        "/today — события на сегодня\n"
        "/week — события на неделю\n"
        "/create — создать встречу\n"
        "/find_slot — найти свободный слот\n"
        "/reschedule — перенести встречу\n"
        "/delete — удалить встречу\n"
        "/accounts — управление аккаунтами\n"
        "/settings — настройки\n"
        "/help — это сообщение",
    )
