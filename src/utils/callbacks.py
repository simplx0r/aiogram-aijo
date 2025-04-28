from aiogram.filters.callback_data import CallbackData
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
import logging

# Импортируем необходимые сервисы и хендлеры
from src.services.link_service import get_link_by_id as db_get_link_by_id, mark_link_published
# Импорт функции отправки перенесен внутрь хендлера, чтобы избежать циклического импорта
# from src.handlers.links import _send_announcement_to_group

logger = logging.getLogger(__name__)

router = Router() # Создаем роутер для колбэков

class PublishLinkCallbackData(CallbackData, prefix="publish_link"):
    link_id: int
    chat_id: int # Используем chat_id для передачи, т.к. CallbackData не любит строки с пробелами

# Добавляем недостающий класс для кнопок ссылки
class LinkCallbackData(CallbackData, prefix="link"):
    action: str # например, 'get_link', 'delete_link'
    link_id: int

class ReminderCallbackData(CallbackData, prefix="reminder"):
    action: str
    link_id: int

class UserStatsCallbackData(CallbackData, prefix="user_stats"):
    user_id: int
    action: str # например, 'view_messages'

@router.callback_query(PublishLinkCallbackData.filter())
async def publish_link_callback_handler(query: CallbackQuery, callback_data: PublishLinkCallbackData, bot: Bot):
    """Обрабатывает нажатие кнопки выбора чата для публикации ссылки."""
    # Отложенный импорт для разрыва цикла
    from src.handlers.links import _send_announcement_to_group

    link_id = callback_data.link_id
    target_chat_id = callback_data.chat_id
    user_id = query.from_user.id

    logger.info(f"User {user_id} initiated publication of link {link_id} to chat {target_chat_id}")

    # 1. Получаем ссылку из БД
    link = await db_get_link_by_id(link_id)
    if not link:
        logger.warning(f"Link {link_id} not found for publication by user {user_id}.")
        await query.answer("Ошибка: Ссылка не найдена!", show_alert=True)
        # Убираем клавиатуру, чтобы избежать повторных нажатий
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass # Игнорируем ошибки редактирования старого сообщения
        return

    if not link.pending:
        logger.warning(f"Link {link_id} is already published or processed, attempted by user {user_id}.")
        await query.answer("Эта ссылка уже была опубликована.", show_alert=True)
        try:
            await query.message.edit_text(f"🔗 Ссылка на '{link.link_url}' уже была опубликована.", reply_markup=None)
        except Exception:
            pass
        return

    # 2. Пытаемся отправить сообщение в выбранную группу
    sent_message = await _send_announcement_to_group(bot, link, target_chat_id)

    if sent_message:
        # 3. Если отправка успешна, обновляем статус ссылки в БД
        publish_success = await mark_link_published(
            link_id=link_id,
            message_id=sent_message.message_id,
            chat_id=sent_message.chat.id
        )

        if publish_success:
            logger.info(f"Successfully published link {link_id} to chat {target_chat_id} by user {user_id}")
            await query.answer("✅ Опубликовано!", show_alert=False)
            # Редактируем исходное сообщение пользователя
            try:
                # Пытаемся получить имя чата для более информативного сообщения
                chat_info = await bot.get_chat(target_chat_id)
                chat_title = chat_info.title or f"чат {target_chat_id}"
            except Exception:
                chat_title = f"чат {target_chat_id}"

            try:
                await query.message.edit_text(
                    f"✅ Ссылка на '{link.link_url}' опубликована в {chat_title}.",
                    reply_markup=None # Убираем клавиатуру
                )
            except Exception as edit_err:
                logger.error(f"Failed to edit original message after publishing link {link_id}: {edit_err}")
        else:
            # Отправка была, но БД не обновилась - критическая ошибка
            logger.error(f"CRITICAL: Sent message for link {link_id} to {target_chat_id}, but FAILED to mark as published in DB! Manual check required.")
            await query.answer("⚠️ Ошибка: Сообщение отправлено, но статус ссылки в базе не обновлен! Свяжитесь с администратором.", show_alert=True)
            # Не редактируем сообщение пользователя, оставляем как есть

    else:
        # 4. Если отправка не удалась
        logger.error(f"Failed to send announcement for link {link_id} to chat {target_chat_id} by user {user_id}.")
        await query.answer("❌ Ошибка отправки сообщения в выбранный чат.", show_alert=True)
        # Можно попробовать отредактировать сообщение пользователя, оставив кнопки
        try:
            await query.message.edit_text(
                f"❌ Не удалось опубликовать ссылку на '{link.link_url}' в выбранный чат. Попробуйте еще раз или выберите другой.",
                reply_markup=query.message.reply_markup # Оставляем кнопки
            )
        except Exception:
            pass # Игнорируем ошибку редактирования
