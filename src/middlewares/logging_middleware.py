# src/middlewares/logging_middleware.py
import time
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, Message, CallbackQuery

from loguru import logger

class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования входящих обновлений и времени их обработки."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject, # Здесь будет Update
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем, что это действительно объект Update
        if not isinstance(event, Update):
            logger.warning(f"Middleware received non-Update event: {type(event)}")
            return await handler(event, data)

        # Извлекаем пользователя и чат, если возможно
        user = data.get('event_from_user')
        chat = data.get('event_chat')

        # Формируем базовую строку лога
        log_prefix = f"Update[{event.update_id}]"
        user_info = f"User[{user.id} @{user.username or ''}]" if user else "User[Unknown]"
        chat_info = f"Chat[{chat.id} {chat.type}]" if chat else "Chat[Unknown]"

        # Определяем тип события
        event_type = "Unknown"
        details = ""
        if event.message:
            event_type = "Message"
            details = f" msg_id={event.message.message_id} type={event.message.content_type}"
            if event.message.text:
                details += f" text='{event.message.text[:30].replace('\n', ' ')}...'"
        elif event.edited_message:
            event_type = "EditedMessage"
            details = f" msg_id={event.edited_message.message_id}"
        elif event.callback_query:
            event_type = "CallbackQuery"
            details = f" data='{event.callback_query.data}' msg_id={event.callback_query.message.message_id if event.callback_query.message else 'N/A'}"
        # Добавьте другие типы событий по мере необходимости (inline_query, chat_member, etc.)

        logger.debug(f"{log_prefix} Received {event_type} from {user_info} in {chat_info}.{details}")

        # Засекаем время начала обработки
        start_time = time.monotonic()

        # Выполняем следующий обработчик в цепочке
        result = await handler(event, data)

        # Засекаем время окончания и логируем длительность
        end_time = time.monotonic()
        duration = (end_time - start_time) * 1000 # в миллисекундах
        logger.debug(f"{log_prefix} Processed {event_type} from {user_info} in {chat_info} in {duration:.2f} ms")

        return result
