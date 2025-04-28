import logging
import os
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, SecretStr, Field, ValidationError


# Основная модель настроек
class Settings(BaseSettings):
    # Поля из TgBotSettings
    bot_token: SecretStr = Field(..., alias='BOT_TOKEN')
    admin_id: int = Field(..., alias='ADMIN_ID')
    main_group_id: int = Field(..., alias='MAIN_GROUP_ID')
    main_topic_id: Optional[int] = Field(None, alias='MAIN_TOPIC_ID')

    # Поля из DbSettings (переименовали url в database_url)
    # database_url больше не используется, задается в services/database.py
    # Можно добавить другие настройки БД сюда, если понадобятся
    # db_echo: bool = Field(False, alias='DB_ECHO') # Пример

    # Конфигурация для загрузки из .env файла (убрали env_nested_delimiter)
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')


# Загружаем настройки и выполняем валидацию
def load_config() -> Settings:
    try:
        settings = Settings()
        # Обновленное логирование
        logging.info(f"Settings loaded: ADMIN_ID={settings.admin_id}, MAIN_GROUP_ID={settings.main_group_id}, MAIN_TOPIC_ID={settings.main_topic_id}")
    except ValidationError as e:
        logging.critical(f"Error loading settings from .env: {e}")
        # Выводим детальную информацию об ошибках валидации
        for error in e.errors():
            logging.critical(f"  Field '{error['loc'][0]}': {error['msg']}")
        exit("Invalid configuration. Check .env file.")

    return settings


# Пример доступа к настройкам (обновленный):
# from src.config import settings # Или load_config()
# token = settings.bot_token.get_secret_value()
# admin = settings.admin_id
# db_url = settings.database_url

# Убедитесь, что DATABASE_URL удалена из .env
# Глобальный экземпляр настроек
settings = load_config()