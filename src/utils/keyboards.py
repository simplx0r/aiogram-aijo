from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hlink
# Повторно исправляем импорт, чтобы убедиться, что он содержит только существующие классы
from .callbacks import PublishLinkCallbackData, ReminderCallbackData, UserStatsCallbackData, LinkCallbackData
from src.db.models import Link # Используем напрямую модель Link
from src.config import settings
from typing import Optional, Dict

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
                callback_data=LinkCallbackData(action="get", link_id=link_id).pack()
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
        callback_data=LinkCallbackData(action="get_link", link_id=link.id).pack()
    )
    reply_markup = builder.as_markup()

    return message_text, reply_markup

# --- Функции для создания клавиатур --- #

def create_publish_keyboard(link_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора чата публикации."""
    builder = InlineKeyboardBuilder()

    # Используем корректное имя атрибута (нижний регистр)
    target_chats = settings.announcement_target_chats

    if not target_chats or not isinstance(target_chats, dict):
        # logger.warning("Словарь announcement_target_chats не найден или пуст в настройках.")
        # Можно вернуть пустую клавиатуру или клавиатуру с сообщением об ошибке
        # builder.button(text="Ошибка: Чаты не настроены", callback_data="error:no_chats")
        return builder.as_markup() # Возвращаем пустую клавиатуру

    # Добавляем кнопки для каждого чата из настроек
    for chat_name, chat_id in target_chats.items():
        callback_data = PublishLinkCallbackData(
            link_id=link_id, chat_id=chat_id
        )
        builder.button(
            text=f"✅ Опубликовать в '{chat_name}'",
            callback_data=callback_data.pack()
        )

    # Можно добавить кнопку отмены
    builder.button(text="❌ Отмена", callback_data=LinkCallbackData(action="cancel_publish", link_id=link_id).pack())
    builder.adjust(1) # По одной кнопке в ряду
    return builder.as_markup()
