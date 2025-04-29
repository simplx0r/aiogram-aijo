# src/utils/messaging.py
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

# Предполагаем, что get_random_phrase находится здесь
from src.utils.misc import get_random_phrase

async def send_link_to_user(bot: Bot, user_id: int, link_url: str, link_id: int) -> tuple[bool, str]:
    """Отправляет ссылку личным сообщением пользователю.

    Args:
        bot: Экземпляр бота.
        user_id: ID пользователя, которому отправляем.
        link_url: URL ссылки для отправки.
        link_id: ID ссылки (для логирования).

    Returns:
        tuple[bool, str]: Кортеж (success: bool, message: str).
                        success=True, message="Ссылка отправлена..."
                        success=False, message="Ошибка: Не могу отправить..."
    """
    # Получаем случайную фразу
    random_phrase = get_random_phrase()
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"{random_phrase}\n{link_url}",
            disable_web_page_preview=False # Включаем превью для ЛС
        )
        logging.info(f"Sent link {link_id} to user {user_id}")
        return True, "Ссылка отправлена вам в личные сообщения!"
    except TelegramBadRequest as e:
        if "bot was blocked by the user" in str(e) or "user not found" in str(e) or "chat not found" in str(e):
            logging.warning(f"Cannot send link {link_id} to user {user_id}: Bot blocked or chat not started.")
            return False, "Не могу отправить вам ссылку. Пожалуйста, начните диалог со мной (напишите /start) и попробуйте снова."
        else:
            logging.error(f"Telegram error sending link {link_id} to user {user_id}: {e}")
            return False, "Произошла ошибка при отправке ссылки."
    except Exception as e:
        logging.exception(f"Unexpected error sending link {link_id} to user {user_id}: {e}")
        return False, "Произошла непредвиденная ошибка."
