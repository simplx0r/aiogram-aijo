# src/scheduler.py
import logging
import datetime
from typing import Optional

import pytz # Для работы с часовыми поясами
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError
from aiogram import Bot # Для отправки сообщений
from aiogram.utils.markdown import hbold
from aiogram.exceptions import TelegramAPIError

# Импортируем необходимые компоненты
from src.db.models import Link
from src.config.config import settings
from src.bot import bot # Импортируем сам объект бота

# --- Настройки часового пояса ---
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# --- Инициализация планировщика ---
# Используем AsyncIOScheduler для работы с asyncio
# Устанавливаем часовой пояс для планировщика
scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)

# --- Функции задач (Jobs) ---

async def send_reminder(link_id: int, minutes_before: int):
    """Отправляет напоминание в основной чат."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from src.utils.callback_data import LinkCallback # Импортируем из utils
    from src.services import get_link_by_id, update_reminder_status # Отложенный импорт

    logging.info(f"Attempting to send {minutes_before}-min reminder for link_id={link_id}")
    link: Optional[Link] = await get_link_by_id(link_id) # Нужна новая функция в db

    if not link:
        logging.warning(f"Link with id={link_id} not found for reminder.")
        return
    if not link.is_active:
        logging.info(f"Link id={link_id} is inactive, skipping reminder.")
        return
    if minutes_before == 30 and link.reminder_30_sent:
        logging.info(f"30-min reminder for link id={link_id} already sent, skipping.")
        return
    if minutes_before == 10 and link.reminder_10_sent:
        logging.info(f"10-min reminder for link id={link_id} already sent, skipping.")
        return

    # Формируем текст напоминания
    reminder_text = (
        f"🕒 {hbold('Напоминание!')}\n"
        f"Через {minutes_before} минут: {link.event_time_str or ''}\n\n"
        f"📢 {hbold('Анонс!')}\n"
        f"{link.announcement_text}"
    )

    try:
        # Создаем клавиатуру с кнопкой "Получить ссылку"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Получить ссылку", callback_data=LinkCallback(action="get_link", link_id=link_id).pack())]
        ])

        # Пытаемся отправить напоминание как новое сообщение или как ответ на исходное?
        # Пока как новое сообщение в тот же топик
        await bot.send_message(
            chat_id=settings.main_group_id,
            text=reminder_text,
            message_thread_id=settings.main_topic_id,
            reply_markup=keyboard, # Добавляем клавиатуру
            disable_web_page_preview=True
            # reply_to_message_id=link.message_id_in_group # Опционально: сделать ответом
        )
        logging.info(f"Sent {minutes_before}-min reminder for link id={link_id} to group {settings.main_group_id}")

        # Обновляем статус отправки в БД
        await update_reminder_status(link_id, minutes_before) # Нужна новая функция в db

    except TelegramAPIError as e:
        logging.error(f"Failed to send {minutes_before}-min reminder for link id={link_id}: {e}")
    except Exception as e:
        logging.exception(f"Unexpected error sending reminder for link id={link_id}: {e}")


# --- Функции управления планировщиком ---

async def schedule_reminders_for_link(link: Link):
    """Планирует задачи напоминаний для конкретной ссылки."""
    assert not link.pending, f"Attempted to schedule reminder for a pending link ID: {link.id}"
    if not link or not link.event_time_utc or not link.id:
        logging.warning(f"Skipping scheduling for invalid link data: {link}")
        return

    event_time_utc_aware = link.event_time_utc
    # Если время из БД наивное (скорее всего), делаем его aware UTC
    if event_time_utc_aware.tzinfo is None:
        event_time_utc_aware = event_time_utc_aware.replace(tzinfo=datetime.timezone.utc)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    link_id = link.id
    job_id_base = f"reminder_link_{link_id}"

    # Планируем 30-минутное напоминание
    if not link.reminder_30_sent:
        reminder_time_30 = event_time_utc_aware - datetime.timedelta(minutes=30)
        if reminder_time_30 > now_utc:
            job_id_30 = f"{job_id_base}_30min"
            try:
                scheduler.add_job(
                    send_reminder,
                    'date', # Запуск один раз в конкретную дату и время
                    run_date=reminder_time_30,
                    args=[link_id, 30],
                    id=job_id_30,
                    replace_existing=True, # Заменить, если задача уже существует
                    misfire_grace_time=60 # Секунды допустимого опоздания
                )
                logging.info(f"Scheduled 30-min reminder for link id={link_id} at {reminder_time_30.astimezone(MOSCOW_TZ)}")
            except Exception as e:
                logging.error(f"Error scheduling 30-min reminder for link id={link_id}: {e}")
        else:
             logging.info(f"30-min reminder time for link id={link_id} is in the past, skipping scheduling.")


    # Планируем 10-минутное напоминание
    if not link.reminder_10_sent:
        reminder_time_10 = event_time_utc_aware - datetime.timedelta(minutes=10)
        if reminder_time_10 > now_utc:
             job_id_10 = f"{job_id_base}_10min"
             try:
                scheduler.add_job(
                    send_reminder,
                    'date',
                    run_date=reminder_time_10,
                    args=[link_id, 10],
                    id=job_id_10,
                    replace_existing=True,
                    misfire_grace_time=60
                )
                logging.info(f"Scheduled 10-min reminder for link id={link_id} at {reminder_time_10.astimezone(MOSCOW_TZ)}")
             except Exception as e:
                 logging.error(f"Error scheduling 10-min reminder for link id={link_id}: {e}")
        else:
            logging.info(f"10-min reminder time for link id={link_id} is in the past, skipping scheduling.")


async def load_scheduled_jobs():
    """Загружает и планирует напоминания для активных ссылок при старте бота."""
    logging.info("Loading scheduled jobs for PUBLISHED links...")
    # Отложенный импорт
    from src.services.link_service import get_active_links_with_reminders
    links = await get_active_links_with_reminders() # Получаем активные и ОПУБЛИКОВАННЫЕ ссылки с временем
    count = 0
    for link in links:
        await schedule_reminders_for_link(link)
        count += 1
    logging.info(f"Scheduled reminders for {count} links.")


def start_scheduler():
    """Запускает планировщик."""
    try:
        if not scheduler.running:
            scheduler.start()
            logging.info("Scheduler started.")
        else:
            logging.info("Scheduler already running.")
    except Exception as e:
        logging.exception(f"Failed to start scheduler: {e}")

def stop_scheduler():
    """Останавливает планировщик."""
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False) # wait=False чтобы не блокировать основной поток при выходе
            logging.info("Scheduler shut down.")
    except Exception as e:
        logging.error(f"Error shutting down scheduler: {e}")
