from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hlink
from .callback_data import LinkCallback, ChatSelectCallback
from src.db.models import Link


class LinkCallbackFactory(CallbackData, prefix="link_action"):
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


# --- Новая функция для форматирования сообщения и кнопки --- #

def format_link_message_with_button(link: Link) -> tuple[str, InlineKeyboardMarkup]:
    """Форматирует текст анонса и создает клавиатуру с кнопкой 'Получить ссылку'."""

    # Формируем текст сообщения
    message_parts = []
    if link.event_time_str:
        message_parts.append(f"**{link.event_time_str}**") # Время жирным
    if link.announcement_text:
        message_parts.append(link.announcement_text)
    else:
        # Если нет текста анонса, используем URL как базовый текст
        message_parts.append(hlink("Ссылка", link.link_url))

    message_text = "\n".join(message_parts)

    # Создаем кнопку
    builder = InlineKeyboardBuilder()
    button_text = "🔗 Получить ссылку"
    # Добавляем URL прямо в текст кнопки для get_link, если нет текста анонса?
    # Или используем стандартный текст всегда?
    # Пока используем стандартный текст.

    # Используем LinkCallback для кнопки, передавая ID основной записи Link
    builder.button(
        text=button_text,
        callback_data=LinkCallback(action="get_link", link_id=link.id).pack()
    )
    reply_markup = builder.as_markup()

    return message_text, reply_markup

# --- Функции для создания клавиатур --- #
