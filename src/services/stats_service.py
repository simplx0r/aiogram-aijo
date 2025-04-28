# src/services/stats_service.py
import logging
import datetime
from typing import Optional, List
import pytz # Добавим pytz для increment_interview_count

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

# Модели и сессия
from src.db.models import GroupMessage, UserStats
from src.services.database import get_session

# --- Функции для логирования сообщений и статистики --- #

async def log_group_message(
    message_id: int,
    chat_id: int,
    user_id: int,
    username: Optional[str],
    message_text: Optional[str],
    timestamp: datetime.datetime
) -> bool:
    """Логирует сообщение из группы и обновляет статистику пользователя."""
    try:
        async with get_session() as session:
            # 1. Логируем само сообщение
            new_message = GroupMessage(
                message_id=message_id,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                message_text=message_text,
                timestamp=timestamp
            )
            session.add(new_message)

            # 2. Обновляем статистику пользователя
            stmt = select(UserStats).where(UserStats.user_id == user_id)
            result = await session.execute(stmt)
            user_stat = result.scalar_one_or_none()

            if user_stat:
                # Обновляем существующую запись
                user_stat.message_count += 1
                user_stat.last_message_timestamp = timestamp
                if username and user_stat.username != username: # Обновляем имя пользователя, если изменилось
                    user_stat.username = username
                logging.debug(f"Incremented message count for existing user {user_id}")
            else:
                # Создаем новую запись
                user_stat = UserStats(
                    user_id=user_id,
                    username=username,
                    message_count=1,
                    interview_count=0, # Инициализируем нулем
                    first_message_timestamp=timestamp,
                    last_message_timestamp=timestamp
                )
                session.add(user_stat)
                logging.debug(f"Created new user stats entry for user {user_id}")

            # await session.flush() # Необязательно здесь, т.к. коммит в конце
        return True
    except SQLAlchemyError as e:
        logging.error(f"Database error logging group message or updating stats for user_id={user_id}: {e}")
        return False
    except Exception as e:
        logging.exception(f"Unexpected error logging group message or updating stats for user_id={user_id}: {e}")
        return False

async def increment_interview_count(user_id: int, username: Optional[str]) -> bool:
    """Увеличивает счетчик собеседований (interview_count) для пользователя."""
    try:
        async with get_session() as session:
            stmt = select(UserStats).where(UserStats.user_id == user_id)
            result = await session.execute(stmt)
            user_stat = result.scalar_one_or_none()

            # Используем UTC для now(), чтобы соответствовать времени сообщений Telegram
            now = datetime.datetime.now(pytz.utc)

            if user_stat:
                # Обновляем существующую запись
                user_stat.interview_count += 1
                user_stat.last_message_timestamp = now # Обновляем время активности
                if username and user_stat.username != username:
                    user_stat.username = username
                logging.info(f"Incremented interview count for existing user {user_id}")
            else:
                # Создаем новую запись, если пользователя нет
                user_stat = UserStats(
                    user_id=user_id,
                    username=username,
                    message_count=0, # Сообщений от бота не считаем
                    interview_count=1,
                    last_message_timestamp=now
                )
                session.add(user_stat)
                logging.info(f"Created new user stats entry and incremented interview count for user {user_id}")

            await session.commit() # Commit changes for both update and add
        return True
    except SQLAlchemyError as e:
        logging.error(f"Database error incrementing interview count for user_id={user_id}: {e}")
        # Rollback in case of error during commit or other operations
        # Although context manager should handle rollback on exceptions, explicit call might be needed depending on exact flow
        # await session.rollback() # Consider adding if necessary, but typically handled by context manager
        return False
    except Exception as e:
        logging.exception(f"Unexpected error incrementing interview count for user_id={user_id}: {e}")
        # await session.rollback()
        return False

# --- Функции для получения статистики --- #

async def get_total_message_count() -> int:
    """Возвращает общее количество сообщений в таблице group_messages."""
    async with get_session() as session:
        try:
            stmt = select(func.count(GroupMessage.id))
            result = await session.execute(stmt)
            count = result.scalar_one_or_none() or 0
            return count
        except SQLAlchemyError as e:
            logging.error(f"Database error getting total message count: {e}")
            return 0
        except Exception as e:
            logging.exception(f"Unexpected error getting total message count: {e}")
            return 0

async def get_total_user_count() -> int:
    """Возвращает общее количество уникальных пользователей в таблице user_stats."""
    async with get_session() as session:
        try:
            stmt = select(func.count(UserStats.user_id))
            result = await session.execute(stmt)
            count = result.scalar_one_or_none() or 0
            return count
        except SQLAlchemyError as e:
            logging.error(f"Database error getting total user count: {e}")
            return 0
        except Exception as e:
            logging.exception(f"Unexpected error getting total user count: {e}")
            return 0

async def get_top_users_by_messages(limit: int = 5) -> List[UserStats]:
    """Возвращает топ пользователей по количеству сообщений."""
    async with get_session() as session:
        try:
            stmt = select(UserStats).order_by(UserStats.message_count.desc()).limit(limit)
            result = await session.execute(stmt)
            users = result.scalars().all()
            return list(users)
        except SQLAlchemyError as e:
            logging.error(f"Database error getting top users by messages: {e}")
            return []
        except Exception as e:
            logging.exception(f"Unexpected error getting top users by messages: {e}")
            return []

async def get_top_users_by_interviews(limit: int = 5) -> List[UserStats]:
    """Возвращает топ пользователей по количеству собеседований."""
    async with get_session() as session:
        try:
            stmt = select(UserStats).order_by(UserStats.interview_count.desc()).limit(limit)
            result = await session.execute(stmt)
            users = result.scalars().all()
            return list(users)
        except SQLAlchemyError as e:
            logging.error(f"Database error getting top users by interviews: {e}")
            return []
        except Exception as e:
            logging.exception(f"Unexpected error getting top users by interviews: {e}")
            return []

async def get_user_stats(user_id: int) -> Optional[UserStats]:
    """Возвращает статистику для конкретного пользователя."""
    async with get_session() as session:
        try:
            stmt = select(UserStats).where(UserStats.user_id == user_id)
            result = await session.execute(stmt)
            user_stats = result.scalar_one_or_none()
            return user_stats
        except SQLAlchemyError as e:
            logging.error(f"Database error getting stats for user_id={user_id}: {e}")
            return None
        except Exception as e:
            logging.exception(f"Unexpected error getting stats for user_id={user_id}: {e}")
            return None
