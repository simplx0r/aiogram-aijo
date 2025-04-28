# src/services/message_log_service.py
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import GroupMessageLog
from src.services.database import get_session

logger = logging.getLogger(__name__)

async def log_group_message(
    user_id: int,
    username: Optional[str],
    full_name: str,
    message_text: str,
    timestamp: datetime
):
    """Записывает лог сообщения из группы в базу данных."""
    async with get_session() as session:
        try:
            log_entry = GroupMessageLog(
                user_id=user_id,
                username=username,
                full_name=full_name,
                message_text=message_text,
                timestamp=timestamp
            )
            session.add(log_entry)
            # Коммит произойдет автоматически при выходе из контекстного менеджера get_session
            logger.debug(f"Logged message from user {user_id} in group.")
        except Exception as e:
            logger.error(f"Failed to log group message from user {user_id}: {e}", exc_info=True)
            # get_session обработает rollback
