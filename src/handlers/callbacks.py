import logging
from aiogram import Router, F, Bot, types
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramAPIError
from src.config import settings
from src.services.link_service import get_link_by_id, publish_link # Импортируем из link_service
from src.utils.callback_data import ChatSelectCallback
from src.utils.keyboards import format_link_message_with_button # Импортируем из keyboards
from aiogram.utils.markdown import hlink

router = Router()

# Обработчик для выбора чата и публикации анонса
@router.callback_query(ChatSelectCallback.filter())
async def handle_publish_link(query: CallbackQuery, callback_data: ChatSelectCallback, bot: Bot):
    """Обрабатывает выбор чата для публикации ссылки."""
    link_id = callback_data.link_id
    target_chat_id = callback_data.target_chat_id
    user_id = query.from_user.id

    logging.info(f"User {user_id} chose chat {target_chat_id} to publish link {link_id}")

    # 1. Получаем ссылку из базы
    link = await get_link_by_id(link_id)

    if not link:
        logging.warning(f"Link ID {link_id} not found when trying to publish by user {user_id}")
        await query.message.edit_text("Ошибка: ссылка не найдена. Возможно, она была удалена.")
        await query.answer(show_alert=True, text="Ошибка: ссылка не найдена.")
        return

    if not link.pending:
        logging.warning(f"Link ID {link_id} is already published. User {user_id} clicked again?")
        await query.message.edit_text(f"Эта ссылка уже опубликована.")
        await query.answer(text="Ссылка уже опубликована.")
        return

    # Находим имя чата по ID из настроек
    target_chats = settings.announcement_target_chats
    chat_name = "Unknown Chat"
    if target_chats and isinstance(target_chats, dict):
        # Правильная итерация по словарю
        for name, chat_id_in_settings in target_chats.items():
            if chat_id_in_settings == target_chat_id:
                chat_name = name
                break
    else:
        logger.warning(f"Target chats dictionary is missing or invalid in settings.")
        await query.answer("Ошибка конфигурации чатов.", show_alert=True)

    # 2. Формируем сообщение для анонса
    message_text, reply_markup = format_link_message_with_button(link)

    # 3. Пытаемся отправить анонс
    try:
        sent_message = await bot.send_message(
            chat_id=target_chat_id,
            text=message_text,
            reply_markup=reply_markup,
            disable_web_page_preview=True # Отключаем предпросмотр для чистоты
        )
        logging.info(f"Sent announcement message {sent_message.message_id} to chat {target_chat_id} for link {link_id}")

        # 4. Публикуем ссылку в базе (обновляем статус, ID, планируем напоминания)
        published_link = await publish_link(
            link_id=link_id,
            chat_id=target_chat_id, # Передаем chat_id правильно
            message_id=sent_message.message_id
        )

        if published_link:
            logging.info(f"Successfully published link {link_id} data in DB.")
            # 5. Сообщаем пользователю об успехе, редактируя исходное сообщение с кнопками
            chat_link = f"https://t.me/c/{str(target_chat_id)[4:]}/{sent_message.message_id}" # Генерируем ссылку на сообщение
            await query.message.edit_text(
                f"✅ Анонс успешно опубликован в чат '{chat_name}'! ({hlink('Перейти', chat_link)})"
            )
            await query.answer("Опубликовано!")
        else:
            logging.error(f"Failed to update link status in DB for link {link_id} after sending message {sent_message.message_id}")
            # Пытаемся удалить отправленное сообщение, чтобы избежать несоответствия?
            try:
                await bot.delete_message(chat_id=target_chat_id, message_id=sent_message.message_id)
                logging.info(f"Deleted message {sent_message.message_id} from chat {target_chat_id} due to DB update failure.")
            except TelegramAPIError as del_e:
                logging.error(f"Failed to delete message {sent_message.message_id} after DB error: {del_e}")
            await query.message.edit_text("⚠️ Произошла ошибка при обновлении статуса ссылки в базе данных после отправки. Анонс не опубликован.")
            await query.answer("Ошибка базы данных после отправки.", show_alert=True)

    except TelegramAPIError as e:
        logging.error(f"Failed to send announcement to chat {target_chat_id} for link {link_id}: {e}", exc_info=True)
        await query.message.edit_text(f"❌ Не удалось отправить анонс в чат '{chat_name}'.\nОшибка: {e.message}. \nВозможно, у бота нет прав на отправку сообщений в этот чат.")
        await query.answer("Ошибка отправки анонса.", show_alert=True)
    except Exception as e:
        logging.error(f"Unexpected error during publishing link {link_id} to chat {target_chat_id}: {e}", exc_info=True)
        await query.message.edit_text("❌ Произошла непредвиденная ошибка при публикации анонса.")
        await query.answer("Непредвиденная ошибка.", show_alert=True)