# src/handlers/link_callbacks.py
import logging
from aiogram import Bot, Router, F
from aiogram.types import CallbackQuery

# Импорты для обработчика
from src.utils.callback_data import LinkCallbackFactory
from src.services.request_log_service import log_link_request as db_log_link_request
from src.services.stats_service import increment_interview_count as db_increment_interview_count
from src.services.link_service import get_link_by_id as db_get_link_by_id
from src.utils.messaging import send_link_to_user # Импорт из нового файла

router = Router() # Создаем новый роутер специально для этих колбэков

@router.callback_query(LinkCallbackFactory.filter(F.action == "get"))
async def get_link(query: CallbackQuery, callback_data: LinkCallbackFactory, bot: Bot):
    """Обработчик нажатия кнопки получения ссылки."""
    user_id = query.from_user.id
    link_id = callback_data.link_id
    username = query.from_user.username or query.from_user.full_name

    logging.info(f"User {user_id} ({username}) requested link_id {link_id}")

    # Логируем запрос в БД и обновляем статистику
    await db_log_link_request(user_id, username, link_id)
    await db_increment_interview_count(user_id, username)

    # Получаем ссылку из БД
    link_record = await db_get_link_by_id(link_id)

    if link_record:
        # Используем функцию отправки из utils
        send_success, message_text = await send_link_to_user(bot, user_id, link_record.link_url, link_id)

        # Отвечаем на колбек
        await query.answer(text=message_text, show_alert=not send_success) # Показываем alert при ошибке

    else:
        logging.warning(f"User {user_id} requested non-existent link_id {link_id}")
        await query.answer(text="Извините, эта ссылка больше не доступна.", show_alert=True)
