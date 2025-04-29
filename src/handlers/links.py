# src/handlers/links.py
import logging
import asyncio
import re
from typing import Optional, NamedTuple
from loguru import logger # Added logger import
from aiogram import Bot, Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.formatting import Text
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hlink

# Утилиты, константы и конфигурация
from src.config.config import settings
from src.utils.constants import URL_REGEX, DATE_REGEX, TIME_REGEX
from src.utils.date_parser import parse_datetime_string, DateTimeParseError, PastDateTimeError
from src.utils.callback_data import ChatSelectCallback, LinkCallbackFactory # Исправлен путь импорта LinkCallbackFactory
from src.utils.keyboards import get_link_keyboard, create_publish_keyboard # Убираем импорт LinkCallbackFactory отсюда
from src.utils.misc import get_random_phrase
from src.db.models import Link

# Сервисы БД
from src.services.link_service import (
    add_link as db_add_link,
    update_link_message_id as db_update_link_message_id,
    get_link_by_id as db_get_link_by_id
)
from src.services.request_log_service import (
    log_link_request as db_log_link_request
)
from src.services.stats_service import (
    increment_interview_count as db_increment_interview_count
)

# Инициализация роутера для этого модуля
router = Router()

# --- НОВОЕ: Структура для аргументов и ошибка парсинга --- #
class AddLinkArgs(NamedTuple):
    link_url: str
    date_str: Optional[str]
    time_str: Optional[str]
    announcement_text: str

class ArgumentParsingError(ValueError):
    """Исключение для ошибок во время парсинга аргументов команды."""
    pass
# --- КОНЕЦ НОВОГО --- #

# --- Вспомогательная функция для парсинга аргументов --- #
def _parse_addlink_args(args_str: Optional[str]) -> AddLinkArgs:
    """Парсит строку аргументов команды /addlink.

    Args:
        args_str: Строка аргументов (command.args).

    Returns:
        AddLinkArgs: Разобранные аргументы.

    Raises:
        ArgumentParsingError: Если парсинг не удался.
    """
    if not args_str:
        raise ArgumentParsingError(
            "Пожалуйста, укажите ссылку после команды.\n"
            "Пример: /addlink https://example.com [ДД.ММ ЧЧ:ММ] [Текст объявления]"
        )

    command_parts = args_str.strip().split()

    link_url: Optional[str] = None
    date_str: Optional[str] = None
    time_str: Optional[str] = None
    announcement_text_parts = []

    current_part_index = 0

    # 1. Ссылка (должна быть первой)
    if current_part_index < len(command_parts) and URL_REGEX.match(command_parts[current_part_index]):
        link_url = command_parts[current_part_index]
        current_part_index += 1
    else:
        raise ArgumentParsingError("Неверный формат ссылки. Ссылка должна начинаться с http:// или https://")

    # 2. Дата (опционально, следующая часть)
    if current_part_index < len(command_parts) and DATE_REGEX.match(command_parts[current_part_index]):
        date_str = command_parts[current_part_index]
        current_part_index += 1

    # 3. Время (опционально, следует за датой ИЛИ если дата не указана, но есть время)
    if current_part_index < len(command_parts) and TIME_REGEX.match(command_parts[current_part_index]):
        is_time_immediately_after_link = (date_str is None and current_part_index == 1)
        is_time_after_date = (date_str is not None and current_part_index == 2)
        if is_time_immediately_after_link or is_time_after_date:
            time_str = command_parts[current_part_index]
            current_part_index += 1

    # 4. Текст объявления (все остальное)
    announcement_text_parts = command_parts[current_part_index:]
    announcement_text = " ".join(announcement_text_parts) if announcement_text_parts else "Анонс"

    # Валидация: если есть дата, должно быть и время, и наоборот
    if (date_str and not time_str) or (not date_str and time_str):
        raise ArgumentParsingError("Для указания времени события необходимо указать и дату, и время (ДД.ММ ЧЧ:ММ). Либо не указывать их вовсе.")

    return AddLinkArgs(
        link_url=link_url,
        date_str=date_str,
        time_str=time_str,
        announcement_text=announcement_text
    )


# --- Вспомогательная функция для отправки анонса в группу --- #
async def _send_announcement_to_group(bot: Bot, link: Link, target_chat_id: int) -> Optional[types.Message]:
    """Отправляет анонс ссылки в указанную группу и обновляет ID сообщения в БД."""
    if not link:
        return None

    # Составляем текст сообщения
    base_text = f"🔗 Новая ссылка от пользователя (ID: {link.added_by_user_id})\n\nURL: {link.link_url}"
    if link.announcement_text:
        group_message_text = f"{base_text}\n\n{link.announcement_text}"
    else:
        group_message_text = base_text

    # Создаем клавиатуру для сообщения в группе
    keyboard = get_link_keyboard(link.id)

    send_kwargs = {
        "chat_id": target_chat_id,
        "text": group_message_text,
        "reply_markup": keyboard,
        "disable_web_page_preview": True
    }

    # --- НОВОЕ: Добавляем message_thread_id, если это основной чат и топик задан --- #
    if settings.main_group_id and settings.main_topic_id and target_chat_id == settings.main_group_id:
        logger.debug(f"Sending to main group {target_chat_id} with topic ID {settings.main_topic_id}")
        send_kwargs["message_thread_id"] = settings.main_topic_id
    # --- КОНЕЦ НОВОГО --- #

    try:
        sent_message = await bot.send_message(**send_kwargs)
        logging.info(f"Sent message for link_id {link.id} to group {target_chat_id}, message_id={sent_message.message_id}")

        # Обновляем message_id и chat_id в базе данных
        # Теперь обновление происходит в callback_handler'е после успешной отправки
        # success = await db_update_link_message_id(link.id, sent_message.message_id, sent_message.chat.id)
        # if success:
        #     return sent_message
        # else:
        #     # Если не удалось обновить ID в БД - это проблема.
        #     logger.error(f"Failed to update message_id {sent_message.message_id} for link_id {link.id} in DB.")
        #     # Попытка удалить некорректное сообщение из группы
        #     try:
        #         await bot.delete_message(chat_id=target_chat_id, message_id=sent_message.message_id)
        #         logger.warning(f"Deleted group message {sent_message.message_id} due to DB update failure.")
        #     except Exception as del_err:
        #         logger.error(f"Failed to delete group message {sent_message.message_id} after DB error: {del_err}")
        #     return None # Сообщение отправлено, но обновление не удалось

        # Возвращаем отправленное сообщение, обновление БД будет в другом месте
        return sent_message

    except TelegramBadRequest as e:
        # --- НОВОЕ: Уточняем логгирование для ошибки TOPIC_CLOSED --- #
        error_message = f"Telegram API error sending link message to group {target_chat_id} for link {link.id}: {e}"
        if "TOPIC_CLOSED" in str(e):
            error_message += " (Check if the target topic exists and is open)"
        logging.error(error_message)
        # --- КОНЕЦ НОВОГО --- #
        return None
    except Exception as e:
        logging.exception(f"Unexpected error sending link message to group {target_chat_id} for link {link.id}: {e}")
        return None


# --- Обработчик команды добавления ссылки --- #

# Обрабатывает команду /addlink или пересылку сообщения для добавления ссылки.
#     Создает 'pending' ссылку и отправляет пользователю клавиатуру для выбора чата публикации.
@router.message(Command("addlink"))
@router.message(F.text & F.text.regexp(URL_REGEX)) # Добавлен обработчик для сообщений с URL
async def handle_add_link(message: Message, command: Optional[CommandObject] = None): 
    """Обрабатывает команду /addlink или пересылку сообщения для добавления ссылки.
    Создает 'pending' ссылку и отправляет пользователю клавиатуру для выбора чата публикации.
    """
    if not message.from_user:
        logger.warning("Received /addlink command without user info.")
        return

    user_id = message.from_user.id
    username = message.from_user.username # Возвращаем присваивание
    first_name = message.from_user.first_name # Возвращаем присваивание
    last_name = message.from_user.last_name # Добавляем присваивание last_name
    user_identifier = username or first_name or str(user_id) # Обновляем user_identifier для полноты

    logger.info(f"Handling link add request from user {user_id} ({user_identifier})")

    link_url: Optional[str] = None
    raw_text: Optional[str] = None

    if message.text:
        link_url_match = URL_REGEX.search(message.text)
        link_url = link_url_match.group(0) if link_url_match else None
        raw_text = message.text # Весь текст для дальнейшего парсинга времени и описания
    elif message.forward_from or message.forward_from_chat:
        if message.forward_from:
            logger.info(f"Received forwarded message from user {message.forward_from.id}")
        elif message.forward_from_chat:
            logger.info(f"Received forwarded message from chat {message.forward_from_chat.id}")
        if message.forward_date:
            logger.info(f"Forwarded message date: {message.forward_date}")
        if message.text:
            link_url_match = URL_REGEX.search(message.text)
            link_url = link_url_match.group(0) if link_url_match else None
            raw_text = message.text # Весь текст для дальнейшего парсинга времени и описания

    if not link_url:
        logger.warning(f"No link found in message from user {message.from_user.id}")
        await message.reply("Не удалось найти ссылку в вашем сообщении.")
        return

    # Извлекаем время и описание
    event_time_str: Optional[str] = None
    event_time_utc: Optional[datetime] = None
    announcement_text: str = link_url # По умолчанию текст - это сама ссылка

    if raw_text:
        time_match = TIME_REGEX.search(raw_text)
        if time_match:
            event_time_str = time_match.group(0)
            announcement_text = raw_text.replace(time_match.group(0), "").replace(link_url, "").strip()
            if not announcement_text: # Если после удаления времени и ссылки ничего не осталось
                announcement_text = link_url
        else:
            # Если времени нет, удаляем только ссылку для получения текста
            announcement_text = raw_text.replace(link_url, "").strip()
            if not announcement_text:
                announcement_text = link_url

    # Добавляем ссылку в базу как 'pending'
    pending_link = await db_add_link(
        user_id=user_id,
        username=username, # Используем переменную
        first_name=first_name, # Используем переменную
        last_name=last_name, # Используем переменную
        link_url=link_url,
        event_time_str=event_time_str,
        event_time_utc=event_time_utc,
        announcement_text=announcement_text
    )

    if not pending_link or not pending_link.id:
        logger.error(f"Failed to create pending link for URL: {link_url} by user {user_id}")
        await message.reply("Произошла ошибка при сохранении ссылки. Попробуйте позже.")
        return

    link_id = pending_link.id
    logger.info(f"Created pending link ID: {link_id} for user {user_id}. URL: {link_url}")

    # Формируем клавиатуру для выбора чата
    target_chats = settings.announcement_target_chats
    if not target_chats:
        logger.warning(f"No target chats configured for announcements. Link ID {link_id} remains pending.")
        await message.reply(f"Ссылка {hlink('сохранена', link_url)}, но нет настроенных чатов для публикации. Обратитесь к администратору.")
        return

    builder = InlineKeyboardBuilder()
    for chat in target_chats:
        builder.button(
            text=chat.name,
            callback_data=ChatSelectCallback(link_id=link_id, target_chat_id=chat.id)
        )
    # Можно добавить кнопку отмены?
    # builder.button(text="Отмена", callback_data=ChatSelectCallback(action="cancel", link_id=link_id))
    builder.adjust(1) # По одной кнопке в ряду

    # Отправляем сообщение пользователю с клавиатурой
    await message.reply(
        f"Куда опубликовать анонс для ссылки: {hlink(announcement_text or link_url, link_url)}?",
        reply_markup=builder.as_markup()
    )
