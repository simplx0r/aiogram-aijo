# src/services/database.py
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Импортируем Base для async_init_db
from src.db.models import Base
# Импортируем загрузчик конфигурации - БОЛЬШЕ НЕ НУЖЕН ДЛЯ URL
# from src.config import load_config # Не нужен для URL, но может понадобиться для других настроек БД

# --- Загрузка конфигурации ---
# settings = load_config() # Не нужен для URL

# --- Настройка SQLAlchemy ---
# Используем фиксированный путь к SQLite базе данных
DATABASE_URL = "sqlite+aiosqlite:///links_bot.db"
engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# --- Функции для инициализации и сессий ---
async def async_init_db():
    """Инициализирует базу данных, создает таблицы, если их нет."""
    async with engine.begin() as conn:
        try:
            # Важно: Убедитесь, что все модели импортированы ДО вызова create_all
            # Обычно это делается в __init__.py пакета models или импортом всех сервисов/хендлеров,
            # которые в свою очередь импортируют модели.
            # В данном случае Base импортирован выше.
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
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logging.error(f"Database session error: {e}. Rolled back transaction.")
            raise
        except Exception as e:
            await session.rollback()
            logging.error(f"An unexpected error occurred in DB session: {e}. Rolled back transaction.")
            raise
        # finally:
            # await session.close() # async_sessionmaker handles closing
