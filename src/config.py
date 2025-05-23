import logging
import os
from typing import Optional, Dict

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field, ValidationError


class Settings(BaseSettings):
    # Используем .env файл и регистронезависимость
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )

    # Обязательные поля
    bot_token: SecretStr = Field(validation_alias='BOT_TOKEN')
    admin_id: int = Field(validation_alias='ADMIN_ID')
    main_group_id: int = Field(validation_alias='MAIN_GROUP_ID')

    # Необязательное поле
    main_topic_id: Optional[int] = Field(None, validation_alias='MAIN_TOPIC_ID')

    # Поле для хранения словаря чатов для анонсов (загружается из JSON)
    announcement_target_chats: Dict[str, int] = Field(
        default_factory=dict, validation_alias='ANNOUNCEMENT_TARGET_CHATS_JSON'
    )

    # Настройки базы данных (если используется PostgreSQL или другая внешняя БД)
    # db_url: str = Field("sqlite+aiosqlite:///./links.db", validation_alias='DATABASE_URL')

    # Настройки логирования (можно добавить позже)
    # LOG_LEVEL: str = 'INFO'


# Загружаем настройки и выполняем валидацию
try:
    settings = Settings()
    # Скроем токен из логов при выводе
    logging.info(f"Settings loaded: ADMIN_ID={settings.admin_id}, MAIN_GROUP_ID={settings.main_group_id}, MAIN_TOPIC_ID={settings.main_topic_id}")
except ValidationError as e:
    logging.critical(f"Error loading settings from .env: {e}")
    # Выводим детальную информацию об ошибках валидации
    for error in e.errors():
        logging.critical(f"  Field '{error['loc'][0]}': {error['msg']}")
    # Прекращаем работу, если конфигурация неверна
    # Можно заменить на raise для обработки в main.py
    exit("Invalid configuration. Check .env file.")


# Пример доступа к настройкам:
# from src.config import settings
# token = settings.bot_token.get_secret_value()
# admin = settings.admin_id
