import logging
import os
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, SecretStr, Field, ValidationError


# Модель для настроек Telegram бота
class TgBotSettings(BaseModel):
    bot_token: SecretStr = Field(..., alias='BOT_TOKEN')
    admin_id: int = Field(..., alias='ADMIN_ID')
    main_group_id: int = Field(..., alias='MAIN_GROUP_ID')
    main_topic_id: Optional[int] = Field(None, alias='MAIN_TOPIC_ID')


# Модель для настроек базы данных
class DbSettings(BaseModel):
    url: str = Field(..., alias='DATABASE_URL')
    # Можно добавить другие настройки БД сюда, если понадобятся
    # echo: bool = Field(False, alias='DB_ECHO') # Пример


# Основная модель настроек, включающая все остальные
class Settings(BaseSettings):
    bot: TgBotSettings
    db: DbSettings

    # Конфигурация для загрузки из .env файла
    model_config = SettingsConfigDict(env_file='.env', env_nested_delimiter='__', extra='ignore')


# Загружаем настройки и выполняем валидацию
def load_config() -> Settings:
    try:
        settings = Settings()
        # Скроем токен из логов при выводе
        logging.info(f"Settings loaded: ADMIN_ID={settings.bot.admin_id}, MAIN_GROUP_ID={settings.bot.main_group_id}, MAIN_TOPIC_ID={settings.bot.main_topic_id}")
    except ValidationError as e:
        logging.critical(f"Error loading settings from .env: {e}")
        # Выводим детальную информацию об ошибках валидации
        for error in e.errors():
            logging.critical(f"  Field '{error['loc'][0]}': {error['msg']}")
        exit("Invalid configuration. Check .env file.")

    return settings


# Пример доступа к настройкам:
# from .config import load_config
# settings = load_config()
# token = settings.bot.bot_token.get_secret_value()
# admin = settings.bot.admin_id
# db_url = settings.db.url