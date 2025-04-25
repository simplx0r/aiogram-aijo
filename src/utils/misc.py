# src/utils/misc.py
import random
import logging
from pathlib import Path

# Определяем путь к файлу с фразами относительно текущего файла
# __file__ -> misc.py
# .parent -> utils/
# .parent -> src/
# / 'data' / 'phrases.txt' -> src/data/phrases.txt
PHRASES_FILE_PATH = Path(__file__).parent.parent / "data" / "phrases.txt"

_phrases_cache = [] # Кэш для фраз

def _load_phrases():
    """Загружает фразы из файла в кэш."""
    global _phrases_cache
    if not PHRASES_FILE_PATH.exists():
        logging.error(f"Phrases file not found at {PHRASES_FILE_PATH}")
        _phrases_cache = ["Ошибка: Файл фраз не найден."] # Запасной вариант
        return
    try:
        with open(PHRASES_FILE_PATH, 'r', encoding='utf-8') as f:
            _phrases_cache = [line.strip() for line in f if line.strip()]
        if not _phrases_cache:
             logging.warning(f"Phrases file {PHRASES_FILE_PATH} is empty.")
             _phrases_cache = ["Файл фраз пуст."] # Запасной вариант
    except Exception as e:
        logging.exception(f"Error loading phrases from {PHRASES_FILE_PATH}: {e}")
        _phrases_cache = ["Ошибка чтения фраз."] # Запасной вариант

def get_random_phrase() -> str:
    """Возвращает случайную фразу из файла src/data/phrases.txt."""
    if not _phrases_cache: # Загружаем при первом вызове
        _load_phrases()

    # Возвращаем случайный элемент из кэша
    try:
        return random.choice(_phrases_cache)
    except IndexError:
        # Это не должно произойти, если _load_phrases отработал,
        # но на всякий случай вернем что-то
        return "Не удалось получить фразу."
