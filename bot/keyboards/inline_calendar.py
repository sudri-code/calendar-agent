from datetime import date, timedelta
import calendar

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

WEEKDAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def build_calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    """Build an inline month-view calendar keyboard."""
    builder = InlineKeyboardBuilder()

    # Header: prev << MONTH YEAR >> next
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    builder.button(text="<<", callback_data=f"cal:nav:{prev_year}:{prev_month}")
    builder.button(text=f"{MONTH_NAMES[month]} {year}", callback_data="cal:ignore")
    builder.button(text=">>", callback_data=f"cal:nav:{next_year}:{next_month}")
    builder.adjust(3)

    # Weekday headers
    for wd in WEEKDAY_NAMES:
        builder.button(text=wd, callback_data="cal:ignore")
    builder.adjust(3, 7)

    # Days
    cal = calendar.monthcalendar(year, month)
    today = date.today()

    day_buttons = []
    for week in cal:
        for day in week:
            if day == 0:
                day_buttons.append((" ", "cal:ignore"))
            else:
                d = date(year, month, day)
                label = str(day)
                if d == today:
                    label = f"[{day}]"
                day_buttons.append((label, f"cal:pick:{year}:{month}:{day}"))

    for label, callback in day_buttons:
        builder.button(text=label, callback_data=callback)

    # Adjust: 3 nav + 7 weekdays + weeks*7
    row_widths = [3, 7] + [7] * len(cal)
    builder.adjust(*row_widths)

    return builder.as_markup()


def build_time_grid_keyboard(selected_hour: int = None) -> InlineKeyboardMarkup:
    """Build a time selection keyboard from 08:00 to 20:00 in 30-min steps."""
    builder = InlineKeyboardBuilder()

    for hour in range(8, 21):
        for minute in (0, 30):
            time_str = f"{hour:02d}:{minute:02d}"
            label = time_str
            builder.button(text=label, callback_data=f"time:pick:{hour}:{minute}")

    builder.adjust(4)
    return builder.as_markup()
