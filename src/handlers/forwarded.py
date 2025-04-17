import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ChatType

from ..config.config import settings # Импортируем настройки

router = Router()

@router.message(F.forward_from_chat, F.chat.type == ChatType.PRIVATE)
async def handle_forwarded_message(message: Message):
    """Обрабатывает пересланные сообщения для получения Topic ID (только от админа)."""
    if message.from_user.id != settings.admin_id:
        # Игнорируем пересылки не от админа
        return

    forwarded_chat = message.forward_from_chat
    # Проверяем, что сообщение переслано из нужной группы
    if forwarded_chat and forwarded_chat.id == settings.main_group_id:
        # Проверяем, есть ли у сообщения message_thread_id (признак топика)
        # Доступ к thread_id может быть через message.forward_origin если это ForumTopicCreated/etc
        # или напрямую если это обычное сообщение из топика
        topic_id = None
        if message.is_topic_message and message.message_thread_id:
            topic_id = message.message_thread_id
        elif message.forward_origin and hasattr(message.forward_origin, 'message_thread_id') and message.forward_origin.message_thread_id:
             topic_id = message.forward_origin.message_thread_id

        if topic_id:
            await message.reply(f"✅ Определен ID топика: `{topic_id}`\n"
                                f"Группа: {forwarded_chat.title} (ID: `{forwarded_chat.id}`)")
            logging.info(f"Admin {message.from_user.id} identified topic ID {topic_id} for group {forwarded_chat.id}")
        else:
            # Сообщение из 'General' или без явного топика
             await message.reply(f"Сообщение переслано из группы {forwarded_chat.title} (ID: `{forwarded_chat.id}`), но не из конкретного топика (возможно, 'General').")
             logging.info(f"Admin {message.from_user.id} forwarded message from General or non-topic in group {forwarded_chat.id}")

    else:
        await message.reply("Пожалуйста, перешлите сообщение из основной группы, указанной в настройках.")