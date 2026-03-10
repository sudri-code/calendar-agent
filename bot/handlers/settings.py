from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import api_client

router = Router()


@router.message(Command("settings"))
@router.message(F.text == "Настройки")
@router.message(F.text == "Календари")
async def cmd_settings(message: Message):
    try:
        calendars = await api_client.get(
            "/api/v1/calendars",
            params={"telegram_user_id": message.from_user.id},
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
        return

    if not calendars:
        await message.answer(
            "Нет подключённых календарей. Сначала подключите Exchange-аккаунт в разделе Аккаунты."
        )
        return

    builder = InlineKeyboardBuilder()
    for cal in calendars:
        mirror_status = "✅" if cal.get("is_mirror_enabled") else "❌"
        active_status = "🟢" if cal.get("is_active") else "⚪"
        label = f"{active_status} {cal['name']} | Зеркало: {mirror_status}"
        builder.button(
            text=label,
            callback_data=f"settings:toggle_mirror:{cal['id']}:{not cal.get('is_mirror_enabled')}",
        )
    builder.adjust(1)

    await message.answer(
        "Настройки календарей:\n(нажмите для переключения зеркалирования)",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("settings:toggle_mirror:"))
async def toggle_mirror(callback: CallbackQuery):
    parts = callback.data.split(":")
    cal_id = parts[2]
    new_value = parts[3] == "True"

    try:
        await api_client.patch(
            f"/api/v1/calendars/{cal_id}",
            json={"is_mirror_enabled": new_value},
            params={"telegram_user_id": callback.from_user.id},
        )
        status = "включено" if new_value else "выключено"
        await callback.answer(f"Зеркалирование {status}")

        # Refresh the settings view
        calendars = await api_client.get(
            "/api/v1/calendars",
            params={"telegram_user_id": callback.from_user.id},
        )
        builder = InlineKeyboardBuilder()
        for cal in calendars:
            mirror_status = "✅" if cal.get("is_mirror_enabled") else "❌"
            active_status = "🟢" if cal.get("is_active") else "⚪"
            label = f"{active_status} {cal['name']} | Зеркало: {mirror_status}"
            builder.button(
                text=label,
                callback_data=f"settings:toggle_mirror:{cal['id']}:{not cal.get('is_mirror_enabled')}",
            )
        builder.adjust(1)
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    except Exception as e:
        await callback.answer(f"Ошибка: {e}")
