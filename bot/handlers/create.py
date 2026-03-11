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


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _overlaps(s1: datetime, e1: datetime, s2: datetime, e2: datetime) -> bool:
    """True if [s1,e1) and [s2,e2) overlap."""
    s1 = s1.replace(tzinfo=None) if s1.tzinfo else s1
    e1 = e1.replace(tzinfo=None) if e1.tzinfo else e1
    s2 = s2.replace(tzinfo=None) if s2.tzinfo else s2
    e2 = e2.replace(tzinfo=None) if e2.tzinfo else e2
    return s1 < e2 and s2 < e1


def _format_conflict(event: dict) -> str:
    s = _parse_dt(event.get("start_at", ""))
    e = _parse_dt(event.get("end_at", ""))
    time_str = ""
    if s and e:
        time_str = f" ({s.strftime('%H:%M')}–{e.strftime('%H:%M')})"
    title = event.get("title", "Без названия")
    attendees = event.get("attendees_json") or []
    att_str = ""
    if 0 < len(attendees) < 5:
        names = [a.get("name") or a.get("email", "") for a in attendees]
        att_str = f"\n   👥 {', '.join(names)}"
    return f"📅 {title}{time_str}{att_str}"

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
    await state.update_data(telegram_user_id=message.from_user.id)
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
                        name = att.get("name", "")
                        contacts = []
                        # Try full name, then progressively strip endings (Russian declension)
                        for trim in range(0, min(4, max(0, len(name) - 3))):
                            q = name[:len(name) - trim] if trim > 0 else name
                            contacts = await api_client.get(
                                "/api/v1/contacts/search",
                                params={"telegram_user_id": message.from_user.id, "q": q},
                            )
                            if contacts:
                                break
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
            # Search contacts with Russian declension fallback
            try:
                contacts = []
                for trim in range(0, min(4, max(0, len(part) - 3))):
                    q = part[:len(part) - trim] if trim > 0 else part
                    contacts = await api_client.get(
                        "/api/v1/contacts/search",
                        params={"telegram_user_id": message.from_user.id, "q": q},
                    )
                    if contacts:
                        break
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


def _get_start_end_title(data: dict) -> tuple[datetime, datetime, str]:
    if data.get("draft"):
        draft = data["draft"]
        return (
            datetime.fromisoformat(draft["start_at"]),
            datetime.fromisoformat(draft["end_at"]),
            draft.get("title", "Встреча"),
        )
    chosen_date = data.get("chosen_date", "")
    chosen_time = data.get("chosen_time", "09:00")
    duration = data.get("duration", 60)
    start = datetime.strptime(f"{chosen_date}T{chosen_time}:00", "%Y-%m-%dT%H:%M:%S")
    return start, start + timedelta(minutes=duration), data.get("title", "Встреча")


def _build_confirm_text(title: str, start: datetime, end: datetime, data: dict) -> str:
    recurrence = data.get("recurrence")
    rec_str = ""
    if recurrence:
        freq_labels = {
            "daily": "ежедневно", "weekly": "еженедельно",
            "monthly": "ежемесячно", "yearly": "ежегодно",
        }
        rec_str = f"\n🔁 Повторяется {freq_labels.get(recurrence.get('frequency'), recurrence.get('frequency', ''))}"

    raw_att = (data.get("draft") or {}).get("attendees") or data.get("attendees") or []
    att_names = [a.get("name") or a.get("email", "") for a in raw_att
                 if a.get("email") and not a.get("email", "").endswith("@unknown")]
    att_str = f"\n<b>Участники:</b> {', '.join(att_names)}" if att_names else ""

    return (
        f"<b>Подтвердите создание встречи:</b>\n\n"
        f"<b>Название:</b> {title}\n"
        f"<b>Начало:</b> {start.strftime('%d.%m.%y %H:%M')}\n"
        f"<b>Конец:</b> {end.strftime('%H:%M')}\n"
        f"{att_str}{rec_str}"
    )


async def _show_confirm(message, state: FSMContext):
    data = await state.get_data()
    start, end, title = _get_start_end_title(data)
    tg_uid = data.get("telegram_user_id") or message.chat.id

    # Check availability
    conflicts = []
    try:
        day_events = await api_client.get(
            "/api/v1/events/day",
            params={"telegram_user_id": tg_uid, "date": start.strftime("%Y-%m-%d")},
        )
        for ev in day_events:
            es = _parse_dt(ev.get("start_at", ""))
            ee = _parse_dt(ev.get("end_at", ""))
            if es and ee and _overlaps(start, end, es, ee):
                conflicts.append(ev)
    except Exception:
        pass

    if conflicts:
        conflict_lines = "\n".join(_format_conflict(c) for c in conflicts[:5])
        text = (
            f"⚠️ <b>В это время уже есть события:</b>\n\n"
            f"{conflict_lines}\n\n"
            f"<b>Планируемая встреча:</b> {title}\n"
            f"{start.strftime('%d.%m.%y %H:%M')} – {end.strftime('%H:%M')}"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="Создать всё равно", callback_data="conflict:proceed")
        builder.button(text="Другие слоты", callback_data="conflict:slots")
        builder.button(text="Отмена", callback_data="confirm:cancel")
        builder.adjust(1)
        await state.set_state(CreateEventStates.conflict)
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        confirm_text = _build_confirm_text(title, start, end, data)
        builder = InlineKeyboardBuilder()
        builder.button(text="Создать", callback_data="confirm:create")
        builder.button(text="Отмена", callback_data="confirm:cancel")
        builder.adjust(2)
        await state.set_state(CreateEventStates.confirm)
        await message.answer(confirm_text, reply_markup=builder.as_markup(), parse_mode="HTML")


def _build_draft_payload(data: dict) -> dict:
    if data.get("draft"):
        draft = dict(data["draft"])
        draft["calendar_id"] = data.get("calendar_id")
        if data.get("recurrence"):
            draft["recurrence"] = data["recurrence"]
        return draft
    chosen_date = data.get("chosen_date", "")
    chosen_time = data.get("chosen_time", "09:00")
    duration = data.get("duration", 60)
    start = datetime.strptime(f"{chosen_date}T{chosen_time}:00", "%Y-%m-%dT%H:%M:%S")
    end = start + timedelta(minutes=duration)
    return {
        "title": data.get("title", "Встреча"),
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "timezone": "UTC",
        "description": data.get("description"),
        "attendees": data.get("attendees", []),
        "calendar_id": data.get("calendar_id"),
        "recurrence": data.get("recurrence"),
    }


async def _do_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    draft = _build_draft_payload(data)
    await callback.message.edit_text("Создаю встречу...")
    try:
        result = await api_client.post(
            "/api/v1/events",
            json=draft,
            params={"telegram_user_id": callback.from_user.id},
        )
        await callback.message.edit_text(
            f"✅ Встреча создана!\n<b>{result.get('title')}</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        await callback.message.edit_text(f"Ошибка при создании встречи: {e}")
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "confirm:create", CreateEventStates.confirm)
async def confirm_create(callback: CallbackQuery, state: FSMContext):
    await _do_create(callback, state)


@router.callback_query(F.data == "conflict:proceed", CreateEventStates.conflict)
async def conflict_proceed(callback: CallbackQuery, state: FSMContext):
    await _do_create(callback, state)


@router.callback_query(F.data == "conflict:slots", CreateEventStates.conflict)
async def conflict_show_slots(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    start, end, title = _get_start_end_title(data)
    duration = int((end - start).total_seconds() // 60)
    tg_uid = data.get("telegram_user_id") or callback.from_user.id

    raw_att = (data.get("draft") or {}).get("attendees") or data.get("attendees") or []
    attendee_emails = [a["email"] for a in raw_att
                       if a.get("email") and not a["email"].endswith("@unknown")]

    await callback.message.edit_text("Ищу свободные слоты...")
    try:
        slots = await api_client.post(
            "/api/v1/events/find-slots",
            json={
                "date_from": start.replace(hour=0, minute=0, second=0).isoformat(),
                "date_to": (start + timedelta(days=3)).replace(hour=23, minute=59, second=59).isoformat(),
                "duration_minutes": duration,
                "attendee_emails": attendee_emails,
            },
            params={"telegram_user_id": tg_uid},
        )
    except Exception as e:
        await callback.message.edit_text(f"Не удалось найти слоты: {e}")
        await callback.answer()
        return

    if not slots:
        await callback.message.edit_text("Свободных слотов не найдено в ближайшие 3 дня.")
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for slot in slots[:6]:
        s = _parse_dt(slot.get("start"))
        e = _parse_dt(slot.get("end"))
        if s and e:
            label = f"{s.strftime('%d.%m %H:%M')} – {e.strftime('%H:%M')}"
            builder.button(text=label, callback_data=f"slot:pick:{slot['start']}:{slot['end']}")
    builder.button(text="Отмена", callback_data="confirm:cancel")
    builder.adjust(1)

    await callback.message.edit_text(
        f"Свободные слоты для «{title}» ({duration} мин):",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("slot:pick:"), CreateEventStates.conflict)
async def slot_picked(callback: CallbackQuery, state: FSMContext):
    _, _, start_str, end_str = callback.data.split(":", 3)
    data = await state.get_data()

    if data.get("draft"):
        draft = dict(data["draft"])
        draft["start_at"] = start_str
        draft["end_at"] = end_str
        await state.update_data(draft=draft)
    else:
        s = datetime.fromisoformat(start_str)
        await state.update_data(
            chosen_date=s.strftime("%Y-%m-%d"),
            chosen_time=s.strftime("%H:%M"),
            duration=int((datetime.fromisoformat(end_str) - s).total_seconds() // 60),
        )

    data = await state.get_data()
    start, end, title = _get_start_end_title(data)
    confirm_text = _build_confirm_text(title, start, end, data)
    builder = InlineKeyboardBuilder()
    builder.button(text="Создать", callback_data="confirm:create")
    builder.button(text="Отмена", callback_data="confirm:cancel")
    builder.adjust(2)
    await state.set_state(CreateEventStates.confirm)
    await callback.message.edit_text(confirm_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "confirm:cancel")
async def confirm_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Создание отменено.")
    await callback.answer()
