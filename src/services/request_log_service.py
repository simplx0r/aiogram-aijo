# src/services/request_log_service.py
import logging
from typing import Optional, List

from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError

# Модели и сессия
from src.db.models import Request
from src.services.database import get_session

# --- Функции для работы с запросами --- #

async def log_link_request(user_id: int, username: Optional[str], link_id: int) -> bool:
    """Логирует запрос пользователя на получение ссылки."""
    try:
        async with get_session() as session:
            new_request = Request(
                user_id=user_id,
                username=username,
                link_id=link_id # Связываем с конкретной ссылкой
            )
            session.add(new_request)
        logging.info(f"Logged link request for user {user_id} ({username}) for link_id {link_id}")
        return True
    except SQLAlchemyError as e:
        logging.error(f"Database error logging link request for user {user_id}, link_id {link_id}: {e}")
        return False
    except Exception as e:
        logging.exception(f"Unexpected error logging link request for user {user_id}, link_id {link_id}: {e}")
        return False
