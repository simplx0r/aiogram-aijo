# src/logging_config.py
import sys
import logging
from pathlib import Path
from loguru import logger

def setup_logging():
    """Настраивает Loguru для красивого логирования."""

    # Определяем базовую директорию проекта, чтобы логи лежали в корне
    BASE_DIR = Path(__file__).resolve().parent.parent
    LOGS_DIR = BASE_DIR / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True) # Создаем папку logs, если нет

    # --- Конфигурация Loguru ---

    # Удаляем стандартный обработчик, чтобы настроить свой
    logger.remove()

    # Настраиваем вывод в консоль (stderr)
    # Добавляем цвета и красивый формат
    logger.add(
        sys.stderr,
        level="DEBUG", # Уровень логирования для консоли (можно изменить на INFO для прода)
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True, # Включаем цвета
        backtrace=True, # Улучшенный трейсбек
        diagnose=True # Расширенная диагностика ошибок
    )

    # Настраиваем вывод в файл
    # Будет создан файл logs/bot.log, ротирующийся при достижении 10 MB
    # и хранящийся 7 дней. Логи уровня INFO и выше.
    logger.add(
        LOGS_DIR / "bot.log",
        level="INFO", # Уровень логирования для файла
        rotation="10 MB", # Ротация файла при достижении 10 MB
        retention="7 days", # Хранить файлы логов 7 дней
        compression="zip", # Сжимать старые логи в zip
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        backtrace=True,
        diagnose=True,
        enqueue=True # Асинхронная запись в файл для производительности
    )

    # --- Перехват стандартного logging ---
    # Это нужно, чтобы логгеры из других библиотек (aiogram, sqlalchemy)
    # тоже направлялись в Loguru.

    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # Получаем соответствующий уровень Loguru
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Находим вызывающий кадр для корректного отображения имени файла и строки
            frame, depth = logging.currentframe(), 2
            # Итерируемся, пока не выйдем из модуля logging
            while frame is not None and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1
            # Если frame стал None, используем стандартную глубину
            if frame is None:
                 depth = 2

            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )

    # Убираем стандартные обработчики logging и добавляем наш перехватчик
    # Устанавливаем уровень 0 для корневого логгера, чтобы перехватывать все
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Настраиваем уровни для некоторых шумных логгеров библиотек (опционально)
    # Уровень DEBUG для aiogram event полезен для отладки, но может быть слишком шумным
    logging.getLogger("aiogram.event").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING) # Делаем SQLAlchemy менее многословным
    # logging.getLogger("httpx").setLevel(logging.WARNING) # Если используется httpx

    logger.info("Logging setup complete using Loguru.")

# Не вызываем setup_logging() здесь, чтобы это делалось явно в main.py
