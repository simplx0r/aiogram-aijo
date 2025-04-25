import datetime
import logging
from typing import Optional

import pytz

# Определяем константы для часовых поясов
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
UTC_TZ = pytz.utc

class DateTimeParseError(ValueError):
    """Custom exception for date/time parsing errors."""
    pass

class PastDateTimeError(DateTimeParseError):
    """Exception for when the parsed date/time is in the past."""
    pass

def parse_datetime_string(date_str: Optional[str], time_str: str) -> datetime.datetime:
    """Парсит строку с датой (опционально) и временем и возвращает datetime UTC.

    Args:
        date_str: Строка с датой (форматы: ДД.ММ, ДД.ММ.ГГГГ, ДД.ММ.ГГ) или None.
        time_str: Строка со временем (формат: ЧЧ:ММ).

    Returns:
        Объект datetime в UTC.

    Raises:
        DateTimeParseError: Если не удалось распознать дату или время.
        PastDateTimeError: Если указанная дата и время уже прошли.
    """
    try:
        parsed_time = datetime.datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        raise DateTimeParseError(f"Не удалось распознать время: {time_str}. Используйте формат ЧЧ:ММ.")

    now_moscow = datetime.datetime.now(MOSCOW_TZ)
    target_date_moscow = now_moscow.date() # По умолчанию - сегодня

    if date_str:
        date_str_normalized = date_str.replace(" ", ".") # Заменяем пробелы на точки
        parsed_date = None
        for fmt in ("%d.%m", "%d.%m.%Y", "%d.%m.%y"):
            try:
                parsed_date = datetime.datetime.strptime(date_str_normalized, fmt).date()
                if fmt == "%d.%m":
                    # Если указан только день и месяц, берем текущий год
                    target_date_moscow = parsed_date.replace(year=now_moscow.year)
                    # Если дата уже прошла в этом году, берем следующий год
                    temp_dt = now_moscow.replace(month=target_date_moscow.month, day=target_date_moscow.day, hour=0, minute=0, second=0, microsecond=0)
                    if temp_dt < now_moscow.replace(hour=0, minute=0, second=0, microsecond=0):
                        target_date_moscow = target_date_moscow.replace(year=now_moscow.year + 1)
                        logging.info(f"Parsed date {date_str} assumed for next year ({target_date_moscow.year}).")
                else:
                    target_date_moscow = parsed_date
                logging.info(f"Using specified date: {target_date_moscow.strftime('%Y-%m-%d')} MSK")
                break # Успешно распарсили, выходим из цикла
            except ValueError:
                continue # Пробуем следующий формат
        if parsed_date is None:
            raise DateTimeParseError(f"Не удалось распознать дату: {date_str}. Используйте формат ДД.ММ или ДД.ММ.ГГГГ.")

    # Создаем datetime с вычисленной датой и указанным временем в МСК
    event_dt_moscow = MOSCOW_TZ.localize(
        datetime.datetime.combine(target_date_moscow, parsed_time)
    )

    # Проверка: не находится ли время в прошлом?
    now_moscow_precise = datetime.datetime.now(MOSCOW_TZ) # Получаем текущее время еще раз для точности

    if not date_str and event_dt_moscow <= now_moscow_precise:
        # Если дата НЕ была указана И время сегодня уже прошло, считаем, что это на завтра
        target_date_moscow += datetime.timedelta(days=1)
        event_dt_moscow = MOSCOW_TZ.localize(
            datetime.datetime.combine(target_date_moscow, parsed_time)
        )
        logging.info(f"Event time {time_str} MSK is for tomorrow ({target_date_moscow.strftime('%Y-%m-%d')}).")

    elif event_dt_moscow <= now_moscow_precise:
        # Если дата была указана (или не указана, но после переноса на завтра все равно в прошлом)
        raise PastDateTimeError(f"Указанная дата и время ({event_dt_moscow.strftime('%d.%m.%Y %H:%M')} МСК) уже прошли.")

    event_dt_utc = event_dt_moscow.astimezone(UTC_TZ)
    logging.info(f"Calculated event time: {event_dt_moscow.strftime('%Y-%m-%d %H:%M:%S %Z%z')} -> {event_dt_utc.strftime('%Y-%m-%d %H:%M:%S %Z%z')}")

    return event_dt_utc
