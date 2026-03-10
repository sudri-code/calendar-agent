from datetime import date, datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.inline_calendar import build_calendar_keyboard, build_time_grid_keyboard
from bot.keyboards.recurrence_keyboard import build_recurrence_choice_keyboard
from bot.services.api_client import api_client
from bot.states.create_states import CreateEventStates

router = Router()

DURATION_OPTIONS = [
    ("15 мин", 15), ("30 мин", 30), ("45 мин", 45),
    ("1 час", 60), ("1.5 ч", 90), ("2 часа", 120),
]


def build_duration_keyboard():
    builder = InlineKeyboardBuilder()
    for label, minutes in DURATION_OPTIONS:
        builder.button(text=label, callback_data=f"dur:{minutes}")
    builder.adjust(3)
    return builder.as_markup()


@router.message(Command("create"))
@router.message(F.text == "Создать встречу")
async def cmd_create(message: Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="Текстом", callback_data="create:mode:text")
    builder.button(text="Пошагово", callback_data="create:mode:step")
    builder.adjust(2)

    await state.set_state(CreateEventStates.choose_mode)
    await message.answer(
        "Как создать встречу?",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "create:mode:text", CreateEventStates.choose_mode)
async def create_text_mode(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateEventStates.enter_title)
    await state.update_data(mode="text")
    await callback.message.edit_text(
        "Опишите встречу текстом, например:\n\n"
        "<i>«Встреча с Иваном завтра в 15:00 на час»</i>\n"
        "<i>«Созвон с командой каждый понедельник в 10:00»</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateEventStates.enter_title, F.text)
async def handle_text_input(message: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("mode", "step")

    if mode == "text":
        # Parse via LLM
        await message.answer("Разбираю ваш запрос...")
        try:
            result = await api_client.post(
                "/api/v1/events/draft/parse",
                params={
                    "text": message.text,
                    "telegram_user_id": message.from_user.id,
                },
            )
            draft = result.get("draft")
            missing = result.get("missing_fields", [])

            if not draft:
                await message.answer(
                    "Не смог разобрать запрос. Попробуйте переформулировать или создайте пошагово."
                )
                await state.clear()
                return

            # Resolve attendees without real emails against contact book
            attendees = draft.get("attendees") or []
            resolved = []
            for att in attendees:
                if att.get("email", "").endswith("@unknown"):
                    try:
                        contacts = await api_client.get(
                            "/api/v1/contacts/search",
                            params={"telegram_user_id": message.from_user.id, "q": att.get("name", "")},
                        )
                        if contacts:
                            resolved.append({"email": contacts[0].get("email", att["email"]), "name": contacts[0].get("name", att.get("name"))})
                        else:
                            resolved.append(att)
                    except Exception:
                        resolved.append(att)
                else:
                    resolved.append(att)
            draft["attendees"] = resolved

            await state.update_data(draft=draft, llm_result=result)

            # Show preview
            rec = draft.get("recurrence")
            rec_str = ""
            if rec:
                freq_labels = {
                    "daily": "ежедневно", "weekly": "еженедельно",
                    "monthly": "ежемесячно", "yearly": "ежегодно",
                }
                rec_str = f"\n🔁 Повторяется {freq_labels.get(rec['frequency'], rec['frequency'])}"

            start = datetime.fromisoformat(draft["start_at"])
            end = datetime.fromisoformat(draft["end_at"])

            att_names = [a.get("name") or a.get("email", "") for a in (draft.get("attendees") or []) if a.get("email") and not a.get("email", "").endswith("@unknown")]
            att_str = f"\n<b>Участники:</b> {', '.join(att_names)}" if att_names else ""

            preview = (
                f"<b>Встреча:</b> {draft.get('title')}\n"
                f"<b>Начало:</b> {start.strftime('%d.%m.%y %H:%M')}\n"
                f"<b>Конец:</b> {end.strftime('%H:%M')}\n"
                f"{att_str}"
                f"{rec_str}"
            )

            if missing:
                preview += f"\n\n<i>Уточните: {', '.join(missing)}</i>"

            # Need calendar selection
            await _ask_calendar(message, state, preview)

        except Exception as e:
            await message.answer(f"Ошибка при разборе: {e}")
            await state.clear()
    else:
        # Step-by-step: title entered
        await state.update_data(title=message.text)
        await _ask_calendar(message, state)


async def _ask_calendar(message: Message, state: FSMContext, prefix: str = ""):
    try:
        calendars = await api_client.get(
            "/api/v1/calendars",
            params={"telegram_user_id": message.from_user.id},
        )
        active_cals = [c for c in calendars if c.get("is_active")]
    except Exception:
        active_cals = []

    if not active_cals:
        await message.answer("Нет активных календарей. Сначала подключите аккаунт и выберите календари.")
        await state.clear()
        return

    builder = InlineKeyboardBuilder()
    for cal in active_cals[:10]:
        builder.button(text=cal["name"], callback_data=f"cal_select:{cal['id']}")
    builder.adjust(1)

    text = (prefix + "\n\n" if prefix else "") + "Выберите основной календарь:"
    await state.set_state(CreateEventStates.choose_calendar)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("cal_select:"), CreateEventStates.choose_calendar)
async def calendar_selected(callback: CallbackQuery, state: FSMContext):
    calendar_id = callback.data.split(":")[1]
    await state.update_data(calendar_id=calendar_id)

    data = await state.get_data()
    if data.get("draft"):
        # Text mode: already have draft, go to recurrence or confirm
        await _show_confirm(callback.message, state)
    else:
        # Step mode: ask date
        today = date.today()
        await state.set_state(CreateEventStates.choose_date)
        await callback.message.edit_text(
            "Выберите дату:",
            reply_markup=build_calendar_keyboard(today.year, today.month),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:pick:"), CreateEventStates.choose_date)
async def date_picked(callback: CallbackQuery, state: FSMContext):
    _, _, year, month, day = callback.data.split(":")
    chosen_date = date(int(year), int(month), int(day))
    await state.update_data(chosen_date=chosen_date.isoformat())
    await state.set_state(CreateEventStates.choose_time)
    await callback.message.edit_text(
        f"Дата: {chosen_date.strftime('%d.%m.%y')}\n\nВыберите время начала:",
        reply_markup=build_time_grid_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:nav:"), CreateEventStates.choose_date)
async def calendar_nav(callback: CallbackQuery, state: FSMContext):
    _, _, year, month = callback.data.split(":")
    await callback.message.edit_reply_markup(
        reply_markup=build_calendar_keyboard(int(year), int(month))
    )
    await callback.answer()


@router.callback_query(F.data == "cal:ignore")
async def calendar_ignore(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("time:pick:"), CreateEventStates.choose_time)
async def time_picked(callback: CallbackQuery, state: FSMContext):
    _, _, hour, minute = callback.data.split(":")
    await state.update_data(chosen_time=f"{int(hour):02d}:{int(minute):02d}")
    await state.set_state(CreateEventStates.choose_duration)
    await callback.message.edit_text(
        "Выберите длительность:",
        reply_markup=build_duration_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dur:"), CreateEventStates.choose_duration)
async def duration_picked(callback: CallbackQuery, state: FSMContext):
    duration = int(callback.data.split(":")[1])
    await state.update_data(duration=duration)
    await state.set_state(CreateEventStates.choose_attendees)
    await callback.message.edit_text(
        "Введите имена или email участников (через запятую), или нажмите /skip для пропуска:"
    )
    await callback.answer()


@router.message(F.text == "/skip", CreateEventStates.choose_attendees)
@router.message(F.text.startswith("/skip"), CreateEventStates.choose_attendees)
async def skip_attendees(message: Message, state: FSMContext):
    await state.update_data(attendees=[])
    await state.set_state(CreateEventStates.enter_title)
    await state.update_data(mode="step")
    await message.answer("Введите название встречи:")


@router.message(CreateEventStates.choose_attendees, F.text)
async def attendees_entered(message: Message, state: FSMContext):
    parts = [p.strip() for p in message.text.split(",") if p.strip()]
    attendees = []
    for part in parts:
        if "@" in part:
            attendees.append({"email": part, "name": None})
        else:
            # Search contacts
            try:
                contacts = await api_client.get(
                    "/api/v1/contacts/search",
                    params={"telegram_user_id": message.from_user.id, "q": part},
                )
                if contacts:
                    c = contacts[0]
                    attendees.append({"email": c.get("email", ""), "name": c.get("name")})
                else:
                    attendees.append({"email": f"{part.replace(' ', '.').lower()}@unknown", "name": part})
            except Exception:
                attendees.append({"email": f"{part.replace(' ', '.').lower()}@unknown", "name": part})

    await state.update_data(attendees=attendees)
    await state.set_state(CreateEventStates.enter_title)
    await state.update_data(mode="step")
    await message.answer("Введите название встречи:")


@router.message(CreateEventStates.enter_title, F.text)
async def title_entered_step(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("mode") == "step":
        await state.update_data(title=message.text)
        await state.set_state(CreateEventStates.enter_description)
        await message.answer("Введите описание (или /skip для пропуска):")


@router.message(CreateEventStates.enter_description)
async def description_entered(message: Message, state: FSMContext):
    desc = None if message.text == "/skip" else message.text
    await state.update_data(description=desc)
    await state.set_state(CreateEventStates.choose_recurrence)
    await message.answer(
        "Настроить повторение?",
        reply_markup=build_recurrence_choice_keyboard(),
    )


@router.callback_query(F.data == "rec:none", CreateEventStates.choose_recurrence)
async def recurrence_none(callback: CallbackQuery, state: FSMContext):
    await state.update_data(recurrence=None)
    await _show_confirm(callback.message, state)
    await callback.answer()


@router.callback_query(
    F.data.in_(["rec:daily", "rec:weekly", "rec:monthly", "rec:yearly"]),
    CreateEventStates.choose_recurrence,
)
async def recurrence_simple(callback: CallbackQuery, state: FSMContext):
    freq_map = {
        "rec:daily": "daily", "rec:weekly": "weekly",
        "rec:monthly": "monthly", "rec:yearly": "yearly",
    }
    freq = freq_map[callback.data]
    recurrence = {"frequency": freq, "interval": 1, "end_type": "no_end"}
    await state.update_data(recurrence=recurrence)
    await _show_confirm(callback.message, state)
    await callback.answer()


async def _show_confirm(message, state: FSMContext):
    data = await state.get_data()

    if data.get("draft"):
        # Text mode
        draft = data["draft"]
        start = datetime.fromisoformat(draft["start_at"])
        end = datetime.fromisoformat(draft["end_at"])
        title = draft.get("title", "Встреча")
        cal_id = data.get("calendar_id", "?")
    else:
        # Step mode
        chosen_date = data.get("chosen_date", "")
        chosen_time = data.get("chosen_time", "09:00")
        duration = data.get("duration", 60)
        title = data.get("title", "Встреча")
        h, m = map(int, chosen_time.split(":"))
        start = datetime.strptime(f"{chosen_date}T{chosen_time}:00", "%Y-%m-%dT%H:%M:%S")
        end = start + timedelta(minutes=duration)
        cal_id = data.get("calendar_id", "?")

    recurrence = data.get("recurrence")
    rec_str = ""
    if recurrence:
        freq_labels = {
            "daily": "ежедневно", "weekly": "еженедельно",
            "monthly": "ежемесячно", "yearly": "ежегодно",
        }
        rec_str = f"\n🔁 Повторяется {freq_labels.get(recurrence.get('frequency'), recurrence.get('frequency', ''))}"

    # Attendees
    if data.get("draft"):
        raw_att = data["draft"].get("attendees") or []
    else:
        raw_att = data.get("attendees") or []
    att_names = [a.get("name") or a.get("email", "") for a in raw_att if a.get("email") and not a.get("email", "").endswith("@unknown")]
    att_str = f"\n<b>Участники:</b> {', '.join(att_names)}" if att_names else ""

    confirm_text = (
        f"<b>Подтвердите создание встречи:</b>\n\n"
        f"<b>Название:</b> {title}\n"
        f"<b>Начало:</b> {start.strftime('%d.%m.%y %H:%M')}\n"
        f"<b>Конец:</b> {end.strftime('%H:%M')}\n"
        f"{att_str}"
        f"{rec_str}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Создать", callback_data="confirm:create")
    builder.button(text="Отмена", callback_data="confirm:cancel")
    builder.adjust(2)

    await state.set_state(CreateEventStates.confirm)
    await message.answer(confirm_text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "confirm:create", CreateEventStates.confirm)
async def confirm_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if data.get("draft"):
        draft = data["draft"]
        draft["calendar_id"] = data.get("calendar_id")
        if data.get("recurrence"):
            draft["recurrence"] = data["recurrence"]
    else:
        chosen_date = data.get("chosen_date", "")
        chosen_time = data.get("chosen_time", "09:00")
        duration = data.get("duration", 60)
        start = datetime.strptime(f"{chosen_date}T{chosen_time}:00", "%Y-%m-%dT%H:%M:%S")
        end = start + timedelta(minutes=duration)
        draft = {
            "title": data.get("title", "Встреча"),
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "timezone": "UTC",
            "description": data.get("description"),
            "attendees": data.get("attendees", []),
            "calendar_id": data.get("calendar_id"),
            "recurrence": data.get("recurrence"),
        }

    await callback.message.edit_text("Создаю встречу...")
    try:
        result = await api_client.post(
            "/api/v1/events",
            json=draft,
            params={"telegram_user_id": callback.from_user.id},
        )
        await callback.message.edit_text(
            f"Встреча создана!\n<b>{result.get('title')}</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        await callback.message.edit_text(f"Ошибка при создании встречи: {e}")

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "confirm:cancel")
async def confirm_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Создание отменено.")
    await callback.answer()
