import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from .config.config import settings # Импортируем наши настройки

# Инициализация хранилища FSM (в памяти)
storage = MemoryStorage()

# Инициализация бота с использованием токена из настроек
# и установкой parse_mode по умолчанию
bot = Bot(
    token=settings.bot_token.get_secret_value(), # Получаем токен безопасно
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Инициализация диспетчера
dp = Dispatcher(storage=storage)

logging.info("Bot and Dispatcher initialized successfully.")