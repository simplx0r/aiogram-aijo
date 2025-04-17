import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramAPIError 
from ..db import database as db

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
    link_db = await db.get_link_by_id(link_id)

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
             await db.log_link_request(
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