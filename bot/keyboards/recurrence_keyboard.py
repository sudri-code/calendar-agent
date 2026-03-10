from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_recurrence_choice_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Не повторять", callback_data="rec:none")
    builder.button(text="Каждый день", callback_data="rec:daily")
    builder.button(text="Каждую неделю", callback_data="rec:weekly")
    builder.button(text="Каждый месяц", callback_data="rec:monthly")
    builder.button(text="Каждый год", callback_data="rec:yearly")
    builder.button(text="Настроить повторение...", callback_data="rec:custom")
    builder.adjust(1, 2, 2, 1)
    return builder.as_markup()


def build_recurrence_mode_keyboard() -> InlineKeyboardMarkup:
    """For editing/deleting recurring events."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Только это событие", callback_data="recmode:single")
    builder.button(text="Это и следующие события", callback_data="recmode:this_and_following")
    builder.button(text="Все события серии", callback_data="recmode:all")
    builder.button(text="Отмена", callback_data="recmode:cancel")
    builder.adjust(1)
    return builder.as_markup()


def build_recurrence_end_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Без конца", callback_data="recend:no_end")
    builder.button(text="По дате", callback_data="recend:by_date")
    builder.button(text="Количество повторений", callback_data="recend:by_count")
    builder.adjust(1)
    return builder.as_markup()


def build_days_keyboard(selected_days: list[str] = None) -> InlineKeyboardMarkup:
    """Build weekday selection keyboard with checkboxes."""
    selected = set(selected_days or [])
    days = [
        ("Пн", "MO"), ("Вт", "TU"), ("Ср", "WE"),
        ("Чт", "TH"), ("Пт", "FR"), ("Сб", "SA"), ("Вс", "SU"),
    ]
    builder = InlineKeyboardBuilder()
    for label, code in days:
        check = "✅" if code in selected else "☐"
        builder.button(text=f"{check} {label}", callback_data=f"day:{code}")
    builder.button(text="Готово", callback_data="day:done")
    builder.adjust(3, 3, 1, 1)
    return builder.as_markup()
