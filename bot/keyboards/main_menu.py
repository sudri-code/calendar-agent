from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Создать встречу"), KeyboardButton(text="Найти слот")],
            [KeyboardButton(text="Мой день"), KeyboardButton(text="Моя неделя")],
            [KeyboardButton(text="Перенести"), KeyboardButton(text="Удалить")],
            [KeyboardButton(text="Аккаунты"), KeyboardButton(text="Календари")],
            [KeyboardButton(text="Контакты"), KeyboardButton(text="Настройки")],
        ],
        resize_keyboard=True,
        persistent=True,
    )
