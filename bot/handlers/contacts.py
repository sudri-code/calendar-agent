from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.services.api_client import api_client

router = Router()


class ContactSearchStates(StatesGroup):
    waiting_query = State()


@router.message(Command("contacts"))
@router.message(F.text == "Контакты")
async def cmd_contacts(message: Message, state: FSMContext):
    await state.set_state(ContactSearchStates.waiting_query)
    await message.answer("Введите имя или email для поиска контакта:")


@router.message(ContactSearchStates.waiting_query)
async def contacts_search(message: Message, state: FSMContext):
    await state.clear()
    query = message.text.strip()
    if not query:
        await message.answer("Запрос не может быть пустым.")
        return

    try:
        contacts = await api_client.get(
            "/api/v1/contacts/search",
            params={"q": query, "telegram_user_id": message.from_user.id},
        )
    except Exception as e:
        await message.answer(f"Ошибка поиска: {e}")
        return

    if not contacts:
        await message.answer(f"Контакты по запросу «{query}» не найдены.")
        return

    lines = [f"Результаты поиска «{query}»:\n"]
    for c in contacts[:10]:
        name = c.get("name") or c.get("displayName") or "—"
        email = c.get("email") or "нет email"
        lines.append(f"• {name} — {email}")

    await message.answer("\n".join(lines))
