# src/services/message_log_service.py
import datetime
from loguru import logger
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import GroupMessageLog
from .database import get_session

async def log_group_message(
    user_id: int,
    username: Optional[str],
    full_name: str,
    message_text: str,
    timestamp: int,
    session: AsyncSession = None
):
    """Logs a message sent in a group chat."""
    close_session = False
    if session is None:
        async with get_session() as session:
            close_session = True

    try:
        # Convert integer timestamp to datetime object
        dt_object = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)

        log_entry = GroupMessageLog(
            user_id=user_id,
            username=username,
            full_name=full_name,
            message_text=message_text,
            timestamp=dt_object  # Use the datetime object here
        )
        session.add(log_entry)
        await session.flush() # Use flush instead of commit if session is passed
        logger.debug(f"Logged message from user {user_id} in group.")
    except Exception as e:
        await session.rollback()
        logger.error(f"Database session error: {e}. Rolled back transaction.")
        logger.error(f"Failed to log group message from user {user_id}: {e}")
    finally:
        if close_session:
             await session.commit() # Commit only if we created the session here
             await session.close()
