# src/services/link_service.py
import logging
import datetime
from typing import Optional, List
import pytz # Добавим pytz для get_pending_reminder_links

from sqlalchemy import update, delete, select
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

# Модели и сессия
from src.db.models import Link # Убрали импорт Request
from src.services.database import get_session
from src.services.stats_service import increment_interview_count # Импорт для статистики

logger = logging.getLogger(__name__)

# --- Функции для работы с Link --- #

async def add_link(user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str],
                  link_url: str,
                  event_time_str: Optional[str] = None,
                  event_time_utc: Optional[datetime.datetime] = None,
                  announcement_text: Optional[str] = None) -> Optional[Link]:
    """Добавляет новую ссылку в базу данных в статусе 'pending'."""
    new_link = Link(
        # posted_message_id и posted_chat_id будут установлены при публикации
        link_url=link_url,
        announcement_text=announcement_text,
        added_by_user_id=user_id,
        event_time_str=event_time_str,
        event_time_utc=event_time_utc,
        is_active=True, # Новая ссылка всегда активна
        pending=True    # Ожидает публикации
    )
    async with get_session() as session:
        try:
            # TODO: Если нужно обновлять статистику пользователя при добавлении ссылки,
            # TODO: вызвать функцию из stats_service.py здесь.

            # Увеличиваем счетчик собеседований для пользователя
            stats_updated = await increment_interview_count(user_id=user_id, username=username)
            if not stats_updated:
                # Логируем ошибку, но продолжаем создание ссылки
                logger.error(f"Не удалось обновить статистику собеседований для пользователя {user_id} при добавлении ссылки.")

            session.add(new_link)
            await session.flush()  # Получаем ID до коммита
            link_id = new_link.id
            await session.commit()
            logger.info(f"Создана ожидающая ссылка ID {link_id}: {link_url} от пользователя {user_id}")
            return new_link
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Ошибка целостности при создании ожидающей ссылки: {e}")
            return None
        except Exception as e:
            await session.rollback()
            logger.error(f"Непредвиденная ошибка при создании ожидающей ссылки: {e}")
            return None

async def publish_link(link_id: int, chat_id: int, message_id: int) -> Optional[Link]:
    """Публикует ссылку: обновляет chat_id, message_id и ставит pending=False."""
    async with get_session() as session:
        try:
            result = await session.execute(
                select(Link).where(Link.id == link_id)
            )
            link = result.scalar_one_or_none()

            if not link:
                logger.warning(f"Попытка опубликовать несуществующую ссылку ID: {link_id}")
                return None

            if not link.pending:
                logger.warning(f"Попытка опубликовать уже опубликованную ссылку ID: {link_id}")
                # Возвращаем ссылку как есть
                return link

            link.posted_chat_id = chat_id
            link.posted_message_id = message_id
            link.pending = False
            # is_active остается True

            await session.commit()
            logger.info(f"Ссылка ID {link_id} опубликована в чат {chat_id}, сообщение {message_id}")
            return link
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при публикации ссылки ID {link_id}: {e}")
            return None

async def get_link_by_id(link_id: int) -> Optional[Link]:
    """Получает ссылку по её первичному ключу (id)."""
    try:
        async with get_session() as session:
            stmt = select(Link).where(Link.id == link_id)
            result = await session.execute(stmt)
            link = result.scalar_one_or_none()
            return link
    except SQLAlchemyError as e:
        logger.error(f"Database error getting link by ID {link_id}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting link by ID {link_id}: {e}")
        return None

async def update_link_message_id(link_id: int, message_id: int, chat_id: int) -> bool:
    """Обновляет posted_message_id и posted_chat_id для существующей ссылки."""
    try:
        async with get_session() as session:
            stmt = (
                update(Link)
                .where(Link.id == link_id)
                .values(posted_message_id=message_id, posted_chat_id=chat_id) # Исправлены имена колонок
                .execution_options(synchronize_session="fetch") # или False, если нет cascade
            )
            result = await session.execute(stmt)
            # Коммит нужен после execute для update/delete/insert
            await session.commit()
            if result.rowcount > 0:
                logger.info(f"Updated message_id={message_id} and chat_id={chat_id} for link_id {link_id}")
                return True
            else:
                logger.warning(f"Attempted to update message/chat_id for non-existent link_id {link_id}")
                return False
    except SQLAlchemyError as e:
        logger.error(f"Database error updating message/chat_id for link_id {link_id}: {e}")
        # Неявный rollback благодаря async with
        return False
    except Exception as e:
        logger.exception(f"Unexpected error updating message/chat_id for link_id {link_id}: {e}")
        # Неявный rollback
        return False

async def update_reminder_status(link_id: int, minutes_before: int) -> bool:
    """Обновляет статус отправки напоминания для ссылки."""
    update_values = {}
    if minutes_before == 60:
        update_values = {'reminder_sent_1h': True}
    elif minutes_before == 15:
        update_values = {'reminder_sent_15m': True}
    else:
        logger.warning(f"Invalid minutes_before value ({minutes_before}) for updating reminder status.")
        return False

    try:
        async with get_session() as session:
            stmt = (
                update(Link)
                .where(Link.id == link_id)
                .values(**update_values)
                .execution_options(synchronize_session=False)
            )
            result = await session.execute(stmt)
            if result.rowcount > 0:
                logger.info(f"Updated reminder_sent_{minutes_before}m for link_id {link_id} to True")
                return True
            else:
                logger.warning(f"Attempted to update reminder status for non-existent link_id {link_id}")
                return False
    except SQLAlchemyError as e:
        logger.error(f"Database error updating reminder status for link_id {link_id}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error updating reminder status for link_id {link_id}: {e}")
        return False

async def get_pending_reminder_links() -> List[Link]:
    """Возвращает активные ссылки, для которых нужны напоминания (время в будущем)."""
    now_utc = datetime.datetime.now(pytz.utc)
    try:
        async with get_session() as session:
            stmt = select(Link).where(
                Link.is_active == True,
                Link.event_time_utc > now_utc
                # Не проверяем флаги reminder_sent_*, это делает планировщик
            )
            result = await session.execute(stmt)
            links = result.scalars().all()
            logger.info(f"Found {len(links)} active links with future event times.")
            return list(links)
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching pending reminder links: {e}")
        return []
    except Exception as e:
        logger.exception(f"Unexpected error fetching pending reminder links: {e}")
        return []

async def get_active_links_with_reminders() -> list[Link]:
    """Возвращает список активных и опубликованных ссылок, у которых установлено время события."""
    async with get_session() as session:
        result = await session.execute(
            select(Link)
            .where(
                Link.is_active == True,
                Link.pending == False, # Добавляем условие, что ссылка опубликована
                Link.event_time_utc != None
            )
        )
        links = result.scalars().all()
        return list(links)

async def mark_link_published(link_id: int, message_id: int, chat_id: int) -> bool:
    """Отмечает ссылку как опубликованную, устанавливая pending=False, posted_message_id и posted_chat_id."""
    try:
        async with get_session() as session:
            stmt = (
                update(Link)
                .where(Link.id == link_id)
                .values(
                    pending=False,
                    posted_message_id=message_id,
                    posted_chat_id=chat_id,
                    updated_at=datetime.datetime.now(datetime.timezone.utc) # Обновляем время изменения
                 )
                .execution_options(synchronize_session="fetch")
            )
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount > 0:
                logger.info(f"Marked link {link_id} as published in chat {chat_id} with message {message_id}")
                return True
            else:
                logger.warning(f"Attempted to mark non-existent or already published link {link_id} as published.")
                return False
    except SQLAlchemyError as e:
        logger.error(f"Database error marking link {link_id} as published: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error marking link {link_id} as published: {e}")
        return False
