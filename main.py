# main.py (New version)
import asyncio
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

# --- Импорт Middleware --- 
from src.middlewares.logging_middleware import LoggingMiddleware

# --- Импорт Loguru --- 
from loguru import logger
from src.logging_config import setup_logging # Импортируем нашу функцию настройки

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
    # Загрузка и планирование ожидающих напоминаний
    await scheduler.schedule_initial_reminders()
    logger.info("Pending reminders scheduled.")
    # Запускаем планировщик
    scheduler.start_scheduler()
    logger.info("Scheduler started.")

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
    # --- Настройка Loguru --- 
    # Вызываем настройку в самом начале, чтобы все логи были перехвачены
    setup_logging()
    
    logger.info("Configuring bot...")

    # Загрузка конфигурации (НОВОЕ)
    settings = load_config()
    
    # --- Регистрация Middleware --- 
    # Важно регистрировать middleware ДО роутеров
    dp.update.outer_middleware(LoggingMiddleware())
    logger.info("Logging middleware registered.")
    
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
    logger.info("Starting bot...") # Лог перед запуском
    # Запускаем основной цикл событий asyncio
    with suppress(KeyboardInterrupt, SystemExit): # Обработка Ctrl+C и sys.exit
        asyncio.run(main())
    logger.info("Bot stopped.") # Лог после остановки