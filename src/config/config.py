import logging
import os
import json
from typing import Optional, List

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, SecretStr, Field, model_validator, ValidationError


# Основная модель настроек
class TargetChat(BaseModel):
    id: int
    name: str


class Settings(BaseSettings):
    # Поля из TgBotSettings
    bot_token: SecretStr = Field(..., alias='BOT_TOKEN')
    admin_id: int = Field(..., alias='ADMIN_ID')
    main_group_id: int = Field(..., alias='MAIN_GROUP_ID') # Оставляем для напоминаний и возможного дефолтного постинга
    main_topic_id: Optional[int] = Field(None, alias='MAIN_TOPIC_ID') # ID темы в main_group_id

    # Список чатов для анонсирования ссылок
    announcement_target_chats_json: str = Field('[]', alias='ANNOUNCEMENT_TARGET_CHATS_JSON') # По умолчанию пустой список
    announcement_target_chats: List[TargetChat] = []

    @model_validator(mode='after')
    def parse_target_chats(self) -> 'Settings':
        """Парсит JSON строку с целевыми чатами в список объектов TargetChat."""
        try:
            chats_data = json.loads(self.announcement_target_chats_json)
            # Убедимся, что это список словарей
            if not isinstance(chats_data, list):
                raise ValueError("JSON должен быть списком объектов")
            self.announcement_target_chats = [TargetChat(**chat) for chat in chats_data]
        except json.JSONDecodeError:
            logging.error(f"Не удалось декодировать JSON из ANNOUNCEMENT_TARGET_CHATS_JSON: {self.announcement_target_chats_json!r}")
            raise ValueError("Неверный формат JSON в ANNOUNCEMENT_TARGET_CHATS_JSON")
        except Exception as e:
            logging.error(f"Ошибка при парсинге ANNOUNCEMENT_TARGET_CHATS_JSON: {e}")
            raise ValueError(f"Ошибка при парсинге целевых чатов: {e}")
        return self

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