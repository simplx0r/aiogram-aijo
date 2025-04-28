import logging
from aiogram import Router, F, Bot, types
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramAPIError
from src.services import get_link_by_id, log_link_request, user_service
from src.utils.callback_data import LinkCallback, ChatSelectCallback
from aiogram.utils.markdown import hlink

router = Router()

@router.callback_query(F.data.startswith("getlink_"))
async def process_get_link_callback(callback_query: CallbackQuery, bot: Bot):
    """Обрабатывает нажатие кнопки 'Получить ссылку', используя БД."""
    user = callback_query.from_user
    try:
        # Получаем ID ССЫЛКИ (первичный ключ) из callback_data
        link_id = int(callback_query.data.split("_")[1])
    except (IndexError, ValueError):
        logging.error(f"Invalid callback_data format: {callback_query.data}")
        await callback_query.answer("Ошибка обработки запроса.", show_alert=True)
        return

    logging.info(f"User {user.id} (@{user.username}) clicked button for link_id {link_id}")

    # 1. Получаем информацию о ссылке из БД по её ID
    link_db = await get_link_by_id(link_id)

    # Проверяем, что ссылка найдена и активна
    if not link_db or not link_db.is_active:
        await callback_query.answer("Извините, эта ссылка больше не актуальна или анонс был удален.", show_alert=True)
        logging.warning(f"User {user.id} tried to get link for inactive/non-existent link_id {link_id}.")
        # Попытка отредактировать старое сообщение, убрав кнопку
        if callback_query.message:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    reply_markup=None # Убираем клавиатуру
                )
            except TelegramAPIError as e:
                # Ошибка может возникнуть, если сообщение слишком старое или удалено
                logging.warning(f"Could not edit outdated message markup for link_id {link_id}: {e}")
        return

    # 2. Проверяем наличие username (Оставляем эту проверку)
    if not user.username:
        await callback_query.answer("Пожалуйста, установите имя пользователя (username) в настройках Telegram, чтобы получить ссылку.", show_alert=True)
        logging.warning(f"User {user.id} (no username) tried to get link for link_id {link_id}.")
        return

    # 3. Отправляем ссылку и логируем в БД
    try:
        await bot.send_message(
            user.id,
            f"Анонс: \"{link_db.announcement_text}\"\n\n"
            f"Держите вашу ссылку: {link_db.link_url}"
        )
        await callback_query.answer("Ссылка отправлена вам в личные сообщения!")
        logging.info(f"Link sent to user {user.id} (@{user.username}) for link_id {link_id}. URL: {link_db.link_url}")

        # Логируем успешный запрос в БД
        # Важно: Используем message_id_in_group для связи с анонсом, если он есть
        if link_db.message_id_in_group:
             await log_link_request(
                user_id=user.id,
                username=user.username,
                link_message_id=link_db.message_id_in_group # Логируем ID анонса
            )
        else:
             logging.warning(f"Could not log request for link_id {link_id} because message_id_in_group is missing.")

    except TelegramAPIError as e:
        # Проверяем специфичную ошибку "Forbidden"
        if "Forbidden: bot can't initiate conversation" in str(e):
            logging.warning(f"User {user.id} (@{user.username}) needs to start the bot first. Link ID: {link_id}")
            await callback_query.answer(
                "Не могу отправить ссылку. Пожалуйста, найдите меня (@{bot_username}) и нажмите 'Start' / 'Запустить'.",
                show_alert=True
            )
        else:
            # Другие ошибки API
            logging.error(f"Failed to send link to user {user.id} (@{user.username}) for link_id {link_id}: {e}")
            await callback_query.answer(
                f"Не удалось отправить ссылку. Ошибка Telegram API.",
                # f"(Ошибка: {e})", # Убрал показ ошибки пользователю
                show_alert=True
            )
    except Exception as e:
        logging.exception(f"Unexpected error in process_get_link_callback for link_id {link_id}: {e}")
        await callback_query.answer("Произошла непредвиденная ошибка при обработке вашего запроса.", show_alert=True)

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

    # Находим имя чата из настроек для сообщения пользователю
    target_chat_name = "Unknown Chat"
    for chat in settings.announcement_target_chats:
        if chat.id == target_chat_id:
            target_chat_name = chat.name
            break

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
        published_link = await user_service.publish_link(
            link_id=link.id,
            target_chat_id=target_chat_id,
            posted_message_id=sent_message.message_id
        )

        if published_link:
            logging.info(f"Successfully published link {link_id} data in DB.")
            # 5. Сообщаем пользователю об успехе, редактируя исходное сообщение с кнопками
            chat_link = f"https://t.me/c/{str(target_chat_id)[4:]}/{sent_message.message_id}" # Генерируем ссылку на сообщение
            await query.message.edit_text(
                f"✅ Анонс успешно опубликован в чат '{target_chat_name}'! ({hlink('Перейти', chat_link)})"
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
        await query.message.edit_text(f"❌ Не удалось отправить анонс в чат '{target_chat_name}'.\nОшибка: {e.message}. \nВозможно, у бота нет прав на отправку сообщений в этот чат.")
        await query.answer("Ошибка отправки анонса.", show_alert=True)
    except Exception as e:
        logging.error(f"Unexpected error during publishing link {link_id} to chat {target_chat_id}: {e}", exc_info=True)
        await query.message.edit_text("❌ Произошла непредвиденная ошибка при публикации анонса.")
        await query.answer("Непредвиденная ошибка.", show_alert=True)