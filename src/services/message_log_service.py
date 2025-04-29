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
    timestamp: datetime.datetime, 
    session: AsyncSession = None
):
    """Logs a message sent in a group chat."""
    close_session = False
    if session is None:
        # Use 'async with' for proper session handling when created internally
        async with get_session() as session:
            close_session = True # Flag that we need to commit/close later

            try:
                # No need to convert timestamp anymore
                # dt_object = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)

                log_entry = GroupMessageLog(
                    user_id=user_id,
                    username=username,
                    full_name=full_name,
                    message_text=message_text,
                    timestamp=timestamp  # Use the datetime object directly
                )
                session.add(log_entry)
                # Commit happens automatically when exiting 'async with get_session()'
                logger.debug(f"Logged message from user {user_id} in group.")
            except Exception as e:
                # Rollback also happens automatically with 'async with'
                logger.error(f"Database session error: {e}. Rolled back transaction.")
                logger.error(f"Failed to log group message from user {user_id}: {e}")
            # No finally block needed, 'async with' handles commit/rollback/close

    else: # session was passed externally
        # Handle the case where the session is passed externally
        try:
            log_entry = GroupMessageLog(
                user_id=user_id,
                username=username,
                full_name=full_name,
                message_text=message_text,
                timestamp=timestamp # Use the datetime object directly
            )
            session.add(log_entry)
            await session.flush() # Use flush as commit is handled by the caller
            logger.debug(f"Logged message from user {user_id} in group.")
        except Exception as e:
            # Let the caller handle rollback if needed
            logger.error(f"Database session error (external session): {e}.")
            logger.error(f"Failed to log group message from user {user_id} (external session): {e}")
            raise # Re-raise the exception for the caller to handle
