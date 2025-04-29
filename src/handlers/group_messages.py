# src/handlers/group_messages.py
import logging
from aiogram import Router, F, types
from ..config.config import settings 
from ..services import log_group_message_stats

router = Router()

router.message.filter(F.chat.id == settings.main_group_id)
router.edited_message.filter(F.chat.id == settings.main_group_id)

# --- Логирование входящих ТЕКСТОВЫХ сообщений ---
@router.message(F.text)
async def log_incoming_text_message(message: types.Message):
    """Логирует новое текстовое сообщение в основном чате."""
    user = message.from_user

    if not user: 
        logging.debug(f"Ignoring message from non-user in group {settings.main_group_id}")
        return

    logging.debug(f"Received text message in group {settings.main_group_id} from user {user.id}.")

    try:
        await log_group_message_stats(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            message_text=message.text, 
            timestamp=message.date 
        )
    except Exception as e:
        logging.error(f"Failed to log incoming group message from user {user.id}: {e}", exc_info=True)


# --- Логирование измененных ТЕКСТОВЫХ сообщений ---
@router.edited_message(F.text)
async def log_edited_text_message(message: types.Message):
    """Логирует изменение текстового сообщения в основном чате."""
    user = message.from_user

    if not user or not message.edit_date: 
        logging.debug(f"Ignoring edited message without user or edit_date in group {settings.main_group_id}")
        return

    logging.debug(f"Received edited text message in group {settings.main_group_id} from user {user.id}.")

    try:
        await log_group_message_stats(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            message_text=message.text, 
            timestamp=message.edit_date 
        )
    except Exception as e:
        logging.error(f"Failed to log edited group message from user {user.id}: {e}", exc_info=True)

# TODO: Можно добавить обработчики на вход/выход участников,
# используя ChatMemberUpdatedFilter, если нужна такая статистика.
