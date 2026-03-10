from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime


def format_event_button(event: dict) -> tuple[str, str]:
    """Format event for inline button display."""
    title = event.get("title", "Без названия")
    if len(title) > 40:
        title = title[:37] + "..."

    start_at = event.get("start_at", "")
    if start_at:
        try:
            dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M")
        except Exception:
            time_str = ""
        label = f"{time_str} {title}"
    else:
        label = title

    return label, event.get("id", "")


def build_event_list_keyboard(events: list[dict], action: str = "select") -> InlineKeyboardMarkup:
    """Build inline keyboard with list of events."""
    builder = InlineKeyboardBuilder()
    for event in events:
        label, event_id = format_event_button(event)
        builder.button(text=label, callback_data=f"event:{action}:{event_id}")
    builder.adjust(1)
    return builder.as_markup()
