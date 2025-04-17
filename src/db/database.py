# src/db/database.py
import logging
import datetime # Добавляем этот импорт
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List
from sqlalchemy import func # Импорт функции для агрегированных запросов

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy import update, delete # Добавляем update и delete
from sqlalchemy.exc import SQLAlchemyError

from .models import Base, Link, Request, GroupMessage, UserStats # Импортируем НОВЫЕ модели

# --- Конфигурация ---
DATABASE_URL = "sqlite+aiosqlite:///./links_bot.db" # Имя файла БД

# --- Настройка SQLAlchemy ---
# Создаем асинхронный движок
engine = create_async_engine(DATABASE_URL, echo=False) # echo=True для отладки SQL запросов

# Создаем фабрику асинхронных сессий
# expire_on_commit=False важно для работы с объектами после коммита в asyncio
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# --- Функции для инициализации и сессий ---
async def async_init_db():
    """Инициализирует базу данных, создает таблицы, если их нет."""
    async with engine.begin() as conn:
        try:
            # Создаем все таблицы, определенные в Base.metadata
            # await conn.run_sync(Base.metadata.drop_all) # Раскомментировать для удаления таблиц при запуске
            await conn.run_sync(Base.metadata.create_all)
            logging.info("Database tables created or already exist.")
        except Exception as e:
            logging.error(f"Error creating database tables: {e}")

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Контекстный менеджер для получения асинхронной сессии."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit() # Коммит транзакции при успешном выходе
        except SQLAlchemyError as e:
            await session.rollback() # Откат при ошибке SQLAlchemy
            logging.error(f"Database session error: {e}. Rolled back transaction.")
            raise # Перевыбрасываем ошибку для обработки выше
        except Exception as e:
            await session.rollback() # Откат при любой другой ошибке
            logging.error(f"An unexpected error occurred in DB session: {e}. Rolled back transaction.")
            raise
        finally:
            await session.close() # Закрытие сессии

# --- Функции для работы с данными (CRUD) ---

async def add_link(message_id: int, link_url: str, announcement_text: str, added_by_user_id: int, event_time_str: Optional[str] = None, event_time_utc: Optional[datetime.datetime] = None) -> Optional[Link]:
    """Добавляет новую ссылку в базу данных."""
    new_link_instance: Optional[Link] = None
    try:
        async with get_session() as session: # get_session сам обработает commit/rollback
            new_link = Link(
                message_id_in_group=message_id,
                link_url=link_url,
                announcement_text=announcement_text,
                added_by_user_id=added_by_user_id,
                event_time_str=event_time_str,
                event_time_utc=event_time_utc,
                is_active=True
            )
            session.add(new_link)
            # Попытка flush/refresh внутри транзакции
            await session.flush() # Отправляет изменения в БД, полезно для получения ID
            await session.refresh(new_link) # Обновляет объект данными из БД
            new_link_instance = new_link # Сохраняем успешно созданный объект
            # Коммит будет выполнен get_session при выходе без ошибок
            logging.info(f"Link prepared in session: message_id={message_id}, url={link_url}")
        # Если мы здесь, get_session успешно выполнил commit
        logging.info(f"Link added to DB successfully: message_id={message_id}, url={link_url}")
        return new_link_instance
    except SQLAlchemyError as e:
        # Ошибка произошла во время flush/refresh или commit (в get_session)
        # get_session уже должен был выполнить rollback
        logging.error(f"Failed to add link to DB (message_id={message_id}): {e}")
        return None # Сигнализируем о неудаче
    except Exception as e:
        # Другие непредвиденные ошибки во время работы с БД
        # get_session также должен выполнить rollback
        logging.error(f"An unexpected error occurred adding link (message_id={message_id}): {e}")
        return None # Сигнализируем о неудаче

async def get_active_link(message_id: int) -> Optional[Link]:
    """Получает активную ссылку по ID сообщения в группе."""
    async with get_session() as session:
        try:
            result = await session.execute(
                select(Link).where(Link.message_id_in_group == message_id, Link.is_active == True)
            )
            link = result.scalar_one_or_none()
            if link:
                logging.debug(f"Active link found for message_id={message_id}")
            else:
                logging.debug(f"No active link found for message_id={message_id}")
            return link
        except SQLAlchemyError as e:
            logging.error(f"Failed to get link from DB (message_id={message_id}): {e}")
            return None

async def log_link_request(user_id: int, username: Optional[str], link_message_id: int):
    """Логирует запрос пользователя на получение ссылки."""
    async with get_session() as session:
        new_request = Request(
            user_id=user_id,
            username=username,
            link_message_id=link_message_id
        )
        session.add(new_request)
        try:
            # await session.commit() # Коммит в get_session
            logging.info(f"Logged request from user {user_id} (@{username}) for link_message_id={link_message_id}")
        except SQLAlchemyError as e:
            logging.error(f"Failed to log request to DB (user_id={user_id}, link_message_id={link_message_id}): {e}")

async def get_all_requests() -> list[Request]:
    """Получает все записи из лога запросов."""
    async with get_session() as session:
        try:
            result = await session.execute(select(Request).order_by(Request.requested_at.desc()))
            requests = list(result.scalars().all()) # Преобразуем в список
            logging.debug(f"Retrieved {len(requests)} request logs from DB.")
            return requests
        except SQLAlchemyError as e:
            logging.error(f"Failed to get requests from DB: {e}")
            return []

# (Опционально) Функция для деактивации ссылки, если понадобится
async def deactivate_link(message_id: int) -> bool:
    """Помечает ссылку как неактивную."""
    async with get_session() as session:
        try:
            result = await session.execute(
                select(Link).where(Link.message_id_in_group == message_id)
            )
            link = result.scalar_one_or_none()
            if link:
                link.is_active = False
                # await session.commit() # Коммит в get_session
                logging.info(f"Deactivated link for message_id={message_id}")
                return True
            else:
                logging.warning(f"Attempted to deactivate non-existent link for message_id={message_id}")
                return False
        except SQLAlchemyError as e:
            logging.error(f"Failed to deactivate link in DB (message_id={message_id}): {e}")
            return False

async def get_link_by_id(link_id: int) -> Optional[Link]:
    """Получает ссылку по её первичному ключу (id)."""
    async with get_session() as session:
        try:
            result = await session.execute(select(Link).where(Link.id == link_id))
            link = result.scalar_one_or_none()
            if link:
                logging.debug(f"Found link by id={link_id}")
            else:
                 logging.debug(f"Link not found by id={link_id}")
            return link
        except SQLAlchemyError as e:
            logging.error(f"Database error getting link by id={link_id}: {e}")
            return None
        except Exception as e:
             logging.exception(f"Unexpected error getting link by id={link_id}: {e}")
             return None

async def update_link_message_id(link_id: int, message_id: int) -> bool:
    """Обновляет message_id_in_group для существующей ссылки."""
    from sqlalchemy import update # Диагностический импорт внутри функции
    async with get_session() as session:
        try:
            stmt = (
                update(Link)
                .where(Link.id == link_id)
                .values(message_id_in_group=message_id)
                .execution_options(synchronize_session="fetch") # Важно для обновления сессии
            )
            result = await session.execute(stmt)

            if result.rowcount == 0:
                logging.warning(f"Link with id={link_id} not found for updating message_id.")
                return False

            logging.info(f"Updated message_id_in_group for link id={link_id} to {message_id}")
            return True

        except SQLAlchemyError as e:
            logging.error(f"Database error updating message_id for link id={link_id}: {e}")
            return False
        except Exception as e:
            logging.exception(f"Unexpected error updating message_id for link id={link_id}: {e}")
            return False

async def update_reminder_status(link_id: int, minutes_before: int) -> bool:
    """Обновляет статус отправки напоминания для ссылки."""
    async with get_session() as session:
        try:
            update_values = {}
            if minutes_before == 30:
                update_values = {Link.reminder_30_sent: True}
            elif minutes_before == 10:
                update_values = {Link.reminder_10_sent: True}
            else:
                logging.warning(f"Invalid minutes_before value ({minutes_before}) for updating reminder status.")
                return False

            stmt = (
                update(Link)
                .where(Link.id == link_id)
                .values(**update_values)
            )
            result = await session.execute(stmt)
            if result.rowcount > 0:
                logging.info(f"Updated {minutes_before}-min reminder status for link id={link_id}")
                return True
            else:
                logging.warning(f"Link id={link_id} not found for updating reminder status.")
                return False
        except SQLAlchemyError as e:
             logging.error(f"Database error updating reminder status for link id={link_id}: {e}")
             return False
        except Exception as e:
             logging.exception(f"Unexpected error updating reminder status for link id={link_id}: {e}")
             return False

async def get_pending_reminder_links() -> List[Link]:
    """Возвращает активные ссылки, для которых нужны напоминания."""
    async with get_session() as session:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            stmt = select(Link).where(
                Link.is_active == True,
                Link.event_time_utc != None, # У события должно быть время
                Link.event_time_utc > now_utc, # Событие еще не наступило
                ( # Или 30-минутное не отправлено ИЛИ 10-минутное не отправлено
                    (Link.reminder_30_sent == False) |
                    (Link.reminder_10_sent == False)
                )
            ).order_by(Link.event_time_utc) # Сортируем по времени события

            result = await session.execute(stmt)
            links = result.scalars().all()
            logging.info(f"Found {len(links)} links with pending reminders.")
            return list(links)
        except SQLAlchemyError as e:
            logging.error(f"Database error getting pending reminder links: {e}")
            return []
        except Exception as e:
             logging.exception(f"Unexpected error getting pending reminder links: {e}")
             return []

async def log_group_message(
    message_id: int,
    chat_id: int,
    user_id: int,
    username: Optional[str],
    message_text: Optional[str],
    timestamp: datetime.datetime
) -> bool:
    """Логирует сообщение из группы и обновляет статистику пользователя."""
    async with get_session() as session:
        try:
            # 1. Log the message
            new_message = GroupMessage(
                message_id=message_id,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                message_text=message_text,
                timestamp=timestamp
            )
            session.add(new_message)
            logging.debug(f"Added GroupMessage to session: msg_id={message_id}, user_id={user_id}")

            # 2. Update User Stats (Upsert logic)
            # Check if user exists
            stmt_select = select(UserStats).where(UserStats.user_id == user_id)
            result = await session.execute(stmt_select)
            user_stats = result.scalar_one_or_none()

            if user_stats:
                # User exists, update count and last_seen
                user_stats.message_count += 1
                user_stats.last_seen = timestamp # Update last seen time
                if user_stats.username != username: # Update username if changed
                    user_stats.username = username
                logging.debug(f"Updating existing UserStats for user_id={user_id}")
            else:
                # User doesn't exist, create new stats record
                user_stats = UserStats(
                    user_id=user_id,
                    username=username,
                    message_count=1,
                    # first_seen uses default, last_seen needs explicit set
                    last_seen = timestamp
                )
                session.add(user_stats)
                logging.debug(f"Creating new UserStats for user_id={user_id}")

            # Session commit is handled by get_session context manager
            return True
        except SQLAlchemyError as e:
            logging.error(f"Database error logging group message (msg_id={message_id}, user_id={user_id}): {e}")
            # Rollback is handled by get_session
            return False
        except Exception as e:
            logging.exception(f"Unexpected error logging group message (msg_id={message_id}, user_id={user_id}): {e}")
            # Rollback is handled by get_session
            return False

async def increment_interview_count(user_id: int, username: Optional[str]) -> bool:
    """Увеличивает счетчик собеседований (interview_count) для пользователя."""
    async with get_session() as session:
        try:
            # Check if user exists
            stmt_select = select(UserStats).where(UserStats.user_id == user_id)
            result = await session.execute(stmt_select)
            user_stats = result.scalar_one_or_none()

            current_time = datetime.datetime.now(datetime.timezone.utc)

            if user_stats:
                # User exists, increment count and update last_seen/username
                user_stats.interview_count += 1
                user_stats.last_seen = current_time
                if user_stats.username != username: # Update username if changed
                    user_stats.username = username
                logging.debug(f"Incremented interview_count for existing UserStats user_id={user_id}")
            else:
                # User doesn't exist, create new stats record with interview_count = 1
                user_stats = UserStats(
                    user_id=user_id,
                    username=username,
                    interview_count=1,
                    message_count=0, # New user via addlink hasn't sent messages yet
                    # first_seen uses default
                    last_seen=current_time
                )
                session.add(user_stats)
                logging.debug(f"Creating new UserStats with interview_count=1 for user_id={user_id}")

            # Session commit is handled by get_session context manager
            return True
        except SQLAlchemyError as e:
            logging.error(f"Database error incrementing interview count for user_id={user_id}: {e}")
            # Rollback is handled by get_session
            return False
        except Exception as e:
            logging.exception(f"Unexpected error incrementing interview count for user_id={user_id}: {e}")
            # Rollback is handled by get_session
            return False

# --- Функции для статистики --- #

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
