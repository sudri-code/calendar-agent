from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import api_client

router = Router()


@router.message(Command("accounts"))
@router.message(F.text == "Аккаунты")
async def accounts_menu(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="Подключить аккаунт", callback_data="accounts:connect")
    builder.button(text="Список аккаунтов", callback_data="accounts:list")
    builder.adjust(1)

    await message.answer(
        "Управление Exchange-аккаунтами:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "accounts:connect")
async def connect_account(callback: CallbackQuery):
    try:
        resp = await api_client.post(
            "/api/v1/accounts/oauth/start",
            params={"telegram_user_id": callback.from_user.id},
        )
        auth_url = resp["auth_url"]

        builder = InlineKeyboardBuilder()
        builder.button(text="Авторизоваться в Microsoft", url=auth_url)

        await callback.message.edit_text(
            "Нажмите кнопку ниже для авторизации Microsoft Exchange:",
            reply_markup=builder.as_markup(),
        )
    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")
    await callback.answer()


@router.callback_query(F.data == "accounts:list")
async def list_accounts(callback: CallbackQuery):
    try:
        accounts = await api_client.get(
            "/api/v1/accounts",
            params={"telegram_user_id": callback.from_user.id},
        )

        if not accounts:
            await callback.message.edit_text("Нет подключённых аккаунтов.")
        else:
            lines = []
            for acc in accounts:
                status_emoji = "✅" if acc["status"] == "active" else "❌"
                lines.append(f"{status_emoji} {acc['email']}")

            builder = InlineKeyboardBuilder()
            builder.button(text="Подключить ещё", callback_data="accounts:connect")

            await callback.message.edit_text(
                "Подключённые аккаунты:\n" + "\n".join(lines),
                reply_markup=builder.as_markup(),
            )
    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")
    await callback.answer()
