# src/utils/constants.py
import re
import pytz

# --- Часовые пояса ---
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
UTC_TZ = pytz.utc

# --- Регулярные выражения ---
# Для валидации ссылки (простое)
URL_REGEX = re.compile(r'https?://\S+')
# Для даты в формате DD.MM или DD.MM.YYYY (с пробелами или точками)
DATE_REGEX = re.compile(r'^(\d{1,2}[.\s]\d{1,2}([.\s]\d{2,4})?)$')
# Для времени в формате HH:MM
TIME_REGEX = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')
