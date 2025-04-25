from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class LinkCallbackFactory(CallbackData, prefix="link"):
    """Фабрика данных для колбеков, связанных со ссылками."""
    action: str # Действие: 'get'
    link_id: int # ID ссылки из базы данных


def get_link_keyboard(link_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой 'Получить ссылку' для указанного link_id."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔗 Получить ссылку",
                callback_data=LinkCallbackFactory(action="get", link_id=link_id).pack()
            )
        ]
    ])
    return keyboard
