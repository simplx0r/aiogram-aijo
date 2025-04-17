# src/handlers/group_messages.py
import logging
import datetime
from aiogram import Router, F, types
from aiogram.filters import ChatMemberUpdatedFilter, KICKED, LEFT, MEMBER, RESTRICTED # Для возможного отслеживания выхода юзеров
from ..db import database as db
from ..config.config import settings # Импортируем settings

router = Router()

# Фильтр, чтобы обработчик срабатывал ТОЛЬКО в нужном чате
router.message.filter(F.chat.id == settings.main_group_id)
router.edited_message.filter(F.chat.id == settings.main_group_id) # Логируем и измененные сообщения

# --- Логирование входящих сообщений ---
@router.message()
async def log_incoming_message(message: types.Message):
    """Логирует любое новое сообщение в основном чате."""
    user = message.from_user
    chat = message.chat
    timestamp_utc = message.date # aiogram message.date is already timezone-aware UTC

    # Не логируем сообщения от самого бота, чтобы избежать зацикливания или лишних данных
    # if user.id == message.bot.id: # Проверить, как получить ID бота правильно, если нужно
    #     return

    logging.debug(f"Received message in group {chat.id} from user {user.id}. Type: {message.content_type}")

    await db.log_group_message(
        message_id=message.message_id,
        chat_id=settings.main_group_id,
        user_id=user.id,
        username=user.username,
        message_text=message.text or message.caption, # Берем текст или подпись к медиа
        timestamp=timestamp_utc
    )
    # Не отвечаем на сообщение, просто логируем

# --- Логирование измененных сообщений ---
@router.edited_message()
async def log_edited_message(message: types.Message):
    """Логирует факт изменения сообщения (пока без сохранения нового текста)."""
    # TODO: При необходимости можно добавить обновление текста в БД,
    # но это усложнит логику (поиск старого сообщения).
    # Пока просто логируем сам факт + обновляем статистику user_stats.
    user = message.from_user
    chat = message.chat
    timestamp_utc = message.edit_date # Время изменения

    if not timestamp_utc: # На всякий случай
        timestamp_utc = datetime.datetime.now(datetime.timezone.utc)

    logging.debug(f"Received edited message in group {settings.main_group_id} from user {user.id}.")

    # Вызываем ту же функцию, чтобы обновить last_seen пользователя и его username,
    # но текст сообщения не передаем, т.к. это изменение существующего.
    # Счетчик сообщений тоже не увеличиваем здесь повторно.
    # Вместо этого можно обновить только UserStats, если нужно.
    # Пока оставим вызов log_group_message, он обновит last_seen и username.
    await db.log_group_message(
        message_id=message.message_id, # ID измененного сообщения
        chat_id=settings.main_group_id,
        user_id=user.id,
        username=user.username,
        message_text=message.text or message.caption, # Сохраняем новый текст/подпись
        timestamp=timestamp_utc
    )

# TODO: Можно добавить обработчики на вход/выход участников,
# используя ChatMemberUpdatedFilter, если нужна такая статистика.
