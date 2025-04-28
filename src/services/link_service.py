# src/services/link_service.py
import logging
import datetime
from typing import Optional, List
import pytz # Добавим pytz для get_pending_reminder_links

from sqlalchemy import update, delete
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

# Модели и сессия
from src.db.models import Link
from src.services.database import get_session

# --- Функции для работы с Link --- #

async def add_link(
    message_id: Optional[int],
    link_url: str,
    announcement_text: str,
    added_by_user_id: int,
    event_time_str: Optional[str] = None,
    event_time_utc: Optional[datetime.datetime] = None
) -> Optional[Link]:
    """Добавляет новую ссылку в базу данных. message_id может быть None сначала."""
    new_link_instance: Optional[Link] = None
    try:
        async with get_session() as session:
            new_link = Link(
                message_id_in_group=message_id, # Может быть None
                link_url=link_url,
                announcement_text=announcement_text,
                added_by_user_id=added_by_user_id,
                event_time_str=event_time_str,
                event_time_utc=event_time_utc,
                is_active=True
            )
            session.add(new_link)
            await session.flush() # Получаем ID до коммита
            await session.refresh(new_link)
            new_link_instance = new_link
            logging.info(f"Link added to session with temp ID {new_link.id} (pending commit)")
        # Коммит произойдет автоматически при выходе из get_session
        if new_link_instance:
            logging.info(f"Successfully added and committed link with ID {new_link_instance.id}")
            return new_link_instance
        else:
            logging.error("Failed to get link instance after flush/refresh.")
            return None
    except SQLAlchemyError as e:
        logging.error(f"Database error adding link (URL: {link_url}): {e}")
        # Rollback handled by get_session
        return None
    except Exception as e:
        logging.exception(f"Unexpected error adding link (URL: {link_url}): {e}")
        # Rollback handled by get_session
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
        logging.error(f"Database error getting link by ID {link_id}: {e}")
        return None
    except Exception as e:
        logging.exception(f"Unexpected error getting link by ID {link_id}: {e}")
        return None

async def update_link_message_id(link_id: int, message_id: int) -> bool:
    """Обновляет message_id_in_group для существующей ссылки."""
    try:
        async with get_session() as session:
            stmt = (
                update(Link)
                .where(Link.id == link_id)
                .values(message_id_in_group=message_id)
                .execution_options(synchronize_session="fetch") # или False, если нет cascade
            )
            result = await session.execute(stmt)
            if result.rowcount > 0:
                logging.info(f"Updated message_id for link_id {link_id} to {message_id}")
                return True
            else:
                logging.warning(f"Attempted to update message_id for non-existent link_id {link_id}")
                return False
    except SQLAlchemyError as e:
        logging.error(f"Database error updating message_id for link_id {link_id}: {e}")
        return False
    except Exception as e:
        logging.exception(f"Unexpected error updating message_id for link_id {link_id}: {e}")
        return False

async def update_reminder_status(link_id: int, minutes_before: int) -> bool:
    """Обновляет статус отправки напоминания для ссылки."""
    update_values = {}
    if minutes_before == 60:
        update_values = {'reminder_sent_1h': True}
    elif minutes_before == 15:
        update_values = {'reminder_sent_15m': True}
    else:
        logging.warning(f"Invalid minutes_before value ({minutes_before}) for updating reminder status.")
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
                logging.info(f"Updated reminder_sent_{minutes_before}m for link_id {link_id} to True")
                return True
            else:
                logging.warning(f"Attempted to update reminder status for non-existent link_id {link_id}")
                return False
    except SQLAlchemyError as e:
        logging.error(f"Database error updating reminder status for link_id {link_id}: {e}")
        return False
    except Exception as e:
        logging.exception(f"Unexpected error updating reminder status for link_id {link_id}: {e}")
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
            logging.info(f"Found {len(links)} active links with future event times.")
            return list(links)
    except SQLAlchemyError as e:
        logging.error(f"Database error fetching pending reminder links: {e}")
        return []
    except Exception as e:
        logging.exception(f"Unexpected error fetching pending reminder links: {e}")
        return []

async def delete_link(link_id: int) -> bool:
    """Удаляет ссылку из базы данных по ID."""
    try:
        async with get_session() as session:
            stmt = delete(Link).where(Link.id == link_id)
            result = await session.execute(stmt)
            if result.rowcount > 0:
                logging.info(f"Deleted link with ID {link_id}")
                # TODO: Подумать о каскадном удалении или удалении связанных Request записей здесь,
                # если cascade='delete' не настроен в модели Link.
                return True
            else:
                logging.warning(f"Attempted to delete non-existent link_id {link_id}")
                return False
    except SQLAlchemyError as e:
        logging.error(f"Database error deleting link ID {link_id}: {e}")
        return False
    except Exception as e:
        logging.exception(f"Unexpected error deleting link ID {link_id}: {e}")
        return False
