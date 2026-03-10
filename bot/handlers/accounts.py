from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.api_client import api_client

router = Router()


class AddAccountStates(StatesGroup):
    enter_server = State()
    enter_username = State()
    enter_password = State()
    enter_email = State()


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
async def connect_account_start(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(AddAccountStates.enter_server)
        await callback.message.edit_text(
            "Введите адрес сервера Exchange (только hostname):\n\n"
            "Пример: <code>mail.company.ru</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        await callback.message.answer(f"Ошибка: <code>{e}</code>", parse_mode="HTML")
    finally:
        await callback.answer()


@router.message(AddAccountStates.enter_server, F.text)
async def account_server_entered(message: Message, state: FSMContext):
    server = message.text.strip().lstrip("https://").lstrip("http://").rstrip("/")
    await state.update_data(ews_server=server)
    await state.set_state(AddAccountStates.enter_email)
    await message.answer(
        "Введите email Exchange-аккаунта:\n\n"
        "Пример: <code>ivanov@company.ru</code>",
        parse_mode="HTML",
    )


@router.message(AddAccountStates.enter_email, F.text)
async def account_email_entered(message: Message, state: FSMContext):
    await state.update_data(email=message.text.strip())
    await state.set_state(AddAccountStates.enter_username)
    await message.answer(
        "Введите имя пользователя для входа:\n\n"
        "Пример: <code>CORP\\ivanov</code> или <code>ivanov@company.ru</code>",
        parse_mode="HTML",
    )


@router.message(AddAccountStates.enter_username, F.text)
async def account_username_entered(message: Message, state: FSMContext):
    await state.update_data(username=message.text.strip())
    await state.set_state(AddAccountStates.enter_password)
    await message.answer(
        "Введите пароль:\n\n"
        "<i>Пароль шифруется и хранится в защищённом виде. "
        "Сообщение с паролем будет удалено.</i>",
        parse_mode="HTML",
    )


@router.message(AddAccountStates.enter_password, F.text)
async def account_password_entered(message: Message, state: FSMContext):
    password = message.text

    # Delete the message with the password immediately
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    await state.clear()

    status_msg = await message.answer("Проверяю подключение к Exchange...")

    try:
        result = await api_client.post(
            "/api/v1/accounts",
            json={
                "email": data["email"],
                "ews_server": data["ews_server"],
                "username": data["username"],
                "password": password,
                "auth_type": "NTLM",
            },
            params={"telegram_user_id": message.from_user.id},
        )
        await status_msg.edit_text(
            f"Аккаунт <b>{result['email']}</b> подключён.\n"
            f"Сервер: <code>{result['ews_server']}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        await status_msg.edit_text(
            f"Не удалось подключиться к Exchange.\n\n"
            f"Ошибка: <code>{e}</code>\n\n"
            "Проверьте адрес сервера, логин и пароль.",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "accounts:list")
async def list_accounts(callback: CallbackQuery):
    try:
        accounts = await api_client.get(
            "/api/v1/accounts",
            params={"telegram_user_id": callback.from_user.id},
        )

        if not accounts:
            builder = InlineKeyboardBuilder()
            builder.button(text="Подключить аккаунт", callback_data="accounts:connect")
            await callback.message.edit_text(
                "Нет подключённых аккаунтов.",
                reply_markup=builder.as_markup(),
            )
        else:
            lines = []
            for acc in accounts:
                status_emoji = "✅" if acc["status"] == "active" else "❌"
                lines.append(f"{status_emoji} {acc['email']} ({acc['ews_server']})")

            builder = InlineKeyboardBuilder()
            builder.button(text="Подключить ещё", callback_data="accounts:connect")

            await callback.message.edit_text(
                "Подключённые аккаунты:\n" + "\n".join(lines),
                reply_markup=builder.as_markup(),
            )
    except Exception as e:
        await callback.message.edit_text(f"Ошибка: {e}")
    await callback.answer()
