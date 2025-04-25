import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from src.config import settings

# Инициализация хранилища FSM (в памяти)
storage = MemoryStorage()

# Инициализация бота с токеном из настроек
# Указываем parse_mode по умолчанию для удобства
bot = Bot(
    token=settings.bot_token.get_secret_value(),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Инициализация диспетчера
dp = Dispatcher(storage=storage)

logging.info("Bot and Dispatcher initialized successfully.")