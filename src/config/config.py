import logging
import os
import json
from typing import Optional, Dict

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, SecretStr, Field, ValidationError


class Settings(BaseSettings):
    # Поля из TgBotSettings
    bot_token: SecretStr = Field(..., alias='BOT_TOKEN')
    admin_id: int = Field(..., alias='ADMIN_ID')
    main_group_id: int = Field(..., alias='MAIN_GROUP_ID') # Оставляем для напоминаний и возможного дефолтного постинга
    main_topic_id: Optional[int] = Field(None, alias='MAIN_TOPIC_ID') # ID темы в main_group_id

    # Use Dict[str, int] directly, Pydantic handles JSON parsing
    announcement_target_chats: Dict[str, int] = Field(
        default_factory=dict, alias='ANNOUNCEMENT_TARGET_CHATS_JSON'
    )

    # Конфигурация для загрузки из .env файла
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')


# Загружаем настройки и выполняем валидацию
def load_config() -> Settings:
    try:
        settings = Settings()
        # Обновленное логирование, добавлено кол-во чатов
        logging.info(f"Settings loaded: ADMIN_ID={settings.admin_id}, MAIN_GROUP_ID={settings.main_group_id}, MAIN_TOPIC_ID={settings.main_topic_id}, TARGET_CHATS_COUNT={len(settings.announcement_target_chats)}")
    except ValidationError as e:
        logging.critical("Error loading settings from .env:")
        # Выводим детальную информацию об ошибках валидации в формате JSON
        logging.critical(e.json(indent=2))
        # Можно перевыбросить исключение для лучшей трассировки или использовать exit
        raise ValueError("Invalid configuration. Check .env file and logs.") from e
        # exit("Invalid configuration. Check .env file.") # Альтернатива

    return settings


# Пример доступа к настройкам (обновленный):
# from src.config import settings # Или load_config()
# token = settings.bot_token.get_secret_value()
# admin = settings.admin_id
# db_url = settings.database_url

# Убедитесь, что DATABASE_URL удалена из .env
# Глобальный экземпляр настроек
settings = load_config()