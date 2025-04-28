# main.py (New version)
import asyncio
import logging
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties # Для указания ParseMode по умолчанию

# Импортируем настройки, обработчики и базу данных
from src.config import load_config # Убрали импорт settings, импортируем load_config
from src.handlers import common, links, stats, callbacks, forwarded, group_messages # Импортируем все роутеры
from src.services.database import async_init_db
from src.bot import bot # Используем наш экземпляр бота
from src import scheduler # Импортируем наш планировщик

# --- Настройка логирования ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout, # Вывод логов в stdout
)
logger = logging.getLogger(__name__)

# --- Инициализация диспетчера ---
# Убрали создание Bot здесь, используем импортированный
dp = Dispatcher()

# --- Функции жизненного цикла ---
async def on_startup(dispatcher: Dispatcher, bot: Bot):
    """Выполняется при запуске бота."""
    logger.info("Starting up...")
    # Импортируем модели ДО инициализации БД, чтобы Base.metadata был полным
    from src.db import models # Явный импорт для регистрации моделей
    logger.info("DB models imported.")
    # Загрузка конфигурации (НОВОЕ)
    settings = load_config()
    # Инициализируем базу данных
    await async_init_db()
    # Загружаем незавершенные напоминания из БД и планируем их
    await scheduler.load_pending_reminders()
    # Запускаем планировщик
    scheduler.start_scheduler()
    logger.info("Scheduler started and pending reminders loaded.")

async def on_shutdown(dispatcher: Dispatcher, bot: Bot):
    """Выполняется при остановке бота."""
    logger.info("Shutting down...")
    # Останавливаем планировщик
    scheduler.stop_scheduler()
    logger.info("Scheduler stopped.")
    # Закрываем сессию бота (если нужно)
    # await bot.session.close() # aiogram >= 3.x handles this automatically? Check docs.
    logger.info("Shutdown complete.")


# --- Основная функция ---
async def main():
    logger.info("Configuring bot...")

    # Загрузка конфигурации (НОВОЕ)
    settings = load_config()

    # Регистрируем роутеры
    dp.include_router(common.router)
    dp.include_router(links.router)
    dp.include_router(stats.router)
    dp.include_router(callbacks.router)
    dp.include_router(forwarded.router)
    dp.include_router(group_messages.router)

    # Регистрируем обработчики жизненного цикла
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting polling...")
    # Удаляем вебхук и пропускаем старые обновления
    await bot.delete_webhook(drop_pending_updates=True)
    # Запускаем поллинг
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Запускаем основной цикл событий asyncio
    with suppress(KeyboardInterrupt, SystemExit): # Обработка Ctrl+C и sys.exit
        asyncio.run(main())