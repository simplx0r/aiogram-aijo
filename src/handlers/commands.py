import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message
from aiogram.enums import ChatType, ParseMode
from aiogram.utils.markdown import hbold, hitalic, hlink
from aiogram.exceptions import TelegramAPIError

from ..bot import bot
from ..config.config import settings
from ..keyboards.inline import get_link_keyboard
from ..db import database as db
from ..db.models import Link, Request
from src.utils.misc import get_random_phrase
from .. import scheduler

import re
import datetime
import pytz
from typing import Optional, List

router = Router()
ADMIN_ID = settings.admin_id
MAIN_GROUP_ID = settings.main_group_id
MAIN_TOPIC_ID = settings.main_topic_id
ZERO_WIDTH_SPACE = "\u200b"
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

TIME_REGEX = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')

@router.message(CommandStart())
async def send_welcome(message: Message):
    """Обработчик команды /start."""
    if message.from_user.id == settings.admin_id:
        await message.answer(f"Привет, {hbold('Администратор')}!\n"
                             f"Я бот для анонса ссылок на конференции.\n"
                             f"Добавить новую ссылку: `/addlink &lt;время&gt; &lt;текст_анонса&gt; &lt;ссылка&gt;`\n"
                             f"Посмотреть запросы: `/showrequests`\n"
                             f"Узнать Topic ID: `/gettopicid`")
    else:
        await message.answer("Привет! Я бот для анонса ссылок на конференции.\n"
                             "Ты можешь добавить ссылку командой `/addlink` в личных сообщениях со мной.")

@router.message(Command("addlink"), F.chat.type == ChatType.PRIVATE)
async def add_link(message: Message, bot: Bot):
    """Обрабатывает команду /addlink <время> <текст_анонса> <ссылка>"""
    if not message.text:
        await message.reply("Пустое сообщение.")
        return

    command_parts = message.text.split() # Разделяем по пробелам
    usage_text = (
        "Неверный формат команды. Использование:\n"
        f"<code>/addlink &lt;время&gt; &lt;текст_анонса&gt; &lt;ссылка&gt;</code>\n"
        f"Пример: <code>/addlink 15:00 Созвон по проекту https://telemost.yandex.ru/j/12345</code>\n"
        f"Время указывается по {hbold('Москве')}. Текст анонса может отсутствовать.\n"
        f"Ссылка должна быть {hbold('последним')} аргументом."
    )

    # Проверяем минимальную длину: /addlink <время> <ссылка> (текст опционален)
    if len(command_parts) < 3:
        await message.reply(usage_text, parse_mode=ParseMode.HTML)
        return

    # Парсим команду по новому формату
    time_str = command_parts[1]
    link_url = command_parts[-1] # Ссылка - последний элемент
    # Текст анонса - все, что между временем и ссылкой
    announcement_text = " ".join(command_parts[2:-1]).strip()

    # Если текст анонса не был предоставлен, он будет пустой строкой ""
    # Можно оставить так или задать значение по умолчанию позже

    if not TIME_REGEX.match(time_str):
        await message.reply(
            f"Неверный формат времени: <code>{time_str}</code>. Укажите время в формате ЧЧ:ММ (например, 09:30 или 23:59).\n"
            f"Время указывается по {hbold('Москве')}.",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        parsed_time = datetime.datetime.strptime(time_str, "%H:%M").time()
        now_moscow = datetime.datetime.now(MOSCOW_TZ)
        # Создаем datetime с текущей датой и указанным временем в МСК
        # .replace() сохраняет tzinfo, поэтому объект УЖЕ будет aware
        event_dt_moscow = now_moscow.replace(
            hour=parsed_time.hour,
            minute=parsed_time.minute,
            second=0,
            microsecond=0
        )

        # Если время сегодня уже прошло, считаем, что это на завтра
        if event_dt_moscow <= now_moscow:
            event_dt_moscow += datetime.timedelta(days=1)
            logging.info(f"Event time {time_str} MSK is for tomorrow.")

        event_dt_utc = event_dt_moscow.astimezone(pytz.utc)
        logging.info(f"Parsed time: {time_str} MSK -> {event_dt_utc} UTC")

    except ValueError as e:
        logging.error(f"Error parsing time string '{time_str}': {e}")
        await message.reply("Произошла ошибка при обработке времени. Убедитесь, что формат верный (ЧЧ:ММ).")
        return
    except Exception as e:
        logging.exception(f"Unexpected error processing time '{time_str}': {e}")
        await message.reply("Произошла внутренняя ошибка при обработке времени.")
        return

    # 3. Сохранение ссылки в БД (ПЕРЕД отправкой анонса)
    new_link: Optional[Link] = await db.add_link(
        message_id=None, # Передаем None, т.к. message_id_in_group пока неизвестен
        link_url=link_url,
        announcement_text=announcement_text, # Оригинальный текст
        added_by_user_id=message.from_user.id,
        event_time_str=time_str,
        event_time_utc=event_dt_utc
    )

    if not new_link:
        await message.reply("Не удалось сохранить информацию о ссылке в базе данных. Анонс не создан.")
        return

    # 4. Формирование текста анонса и клавиатуры (ПОСЛЕ получения link_id)
    try:
        # Удаляем ссылки Yandex Telemost из публичного текста
        telemost_pattern = r'https?://telemost\.yandex\.ru/\S+'
        public_announcement_text = re.sub(telemost_pattern, '', announcement_text).strip()

        # Если после удаления ничего не осталось И текст ИЗНАЧАЛЬНО был пустым,
        # ставим заглушку. Если текст был, но содержал только ссылку - оставляем пустым.
        if not public_announcement_text and not announcement_text:
            public_announcement_text = "(Описание встречи)"

        keyboard = get_link_keyboard(link_id=new_link.id)
        tags = f"{ZERO_WIDTH_SPACE}#анонс {ZERO_WIDTH_SPACE}#ссылка"
        full_announcement_text = (
            f"📅 {hbold(event_dt_moscow.strftime('%d.%m'))} 🕒 {hbold(time_str)} MSK\n\n"
            # Используем ОЧИЩЕННЫЙ текст для публикации
            f"{public_announcement_text}\n\n"
            f"{tags}"
        )

        # 5. Отправка анонса в группу
        announcement_msg = await bot.send_message(
            chat_id=settings.main_group_id, # ИСПОЛЬЗУЕМ settings
            text=full_announcement_text,
            message_thread_id=settings.main_topic_id, # ИСПОЛЬЗУЕМ settings
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        logging.info(f"Announcement sent for link id={new_link.id} to group {settings.main_group_id}. Message ID: {announcement_msg.message_id}")

        # Обновляем message_id в БД после успешной отправки
        await db.update_link_message_id(new_link.id, announcement_msg.message_id)
        logging.info(f"Updated message_id_in_group for link id={new_link.id} to {announcement_msg.message_id}")

    except Exception as e:
        logging.exception(f"Failed to send announcement for link id={new_link.id} to group {settings.main_group_id}: {e}")
        # Ссылка уже в БД (с message_id=None), но анонс не ушел.
        # Можно добавить логику компенсации или уведомление администратору.
        await message.reply(
            "Ссылка сохранена в базе данных, но произошла ошибка при отправке анонса в группу. "
            "Свяжитесь с администратором.",
            parse_mode=ParseMode.HTML
        )
        return # Прерываем выполнение здесь, т.к. основная операция не завершена

    # Если все прошло успешно
    await message.reply(
        f"✅ Анонс для ссылки <a href=\"{link_url}\">{announcement_text}</a> ({time_str} МСК) успешно создан в группе.",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

    # УВЕЛИЧИВАЕМ СЧЕТЧИК СОБЕСЕДОВАНИЙ ПОЛЬЗОВАТЕЛЯ
    await db.increment_interview_count(
        user_id=message.from_user.id,
        username=message.from_user.username
    )
    logging.info(f"Incremented interview count for user {message.from_user.id}")

    # 6. Планирование напоминаний
    try:
        await scheduler.schedule_reminders_for_link(new_link)
        logging.info(f"Scheduled reminders for link id={new_link.id}")
    except Exception as e:
         logging.exception(f"Failed to schedule reminders for link id={new_link.id}: {e}")

@router.message(Command("showrequests"), F.from_user.id == ADMIN_ID)
async def show_requests(message: Message):
    """Показывает последние запросы ссылок (только для админа)."""
    logging.info(f"Admin {message.from_user.id} requested logs.")
    requests_list: List[Request] = await db.get_all_requests()

    if not requests_list:
        await message.reply("Запросы ссылок пока отсутствуют.")
        return

    response_lines = [f"{hbold('Последние запросы ссылок:')}\n"] 
    for i, req in enumerate(requests_list[:20]): 
        req_time_msk = req.requested_at.astimezone(MOSCOW_TZ)
        time_str = req_time_msk.strftime("%Y-%m-%d %H:%M:%S MSK")
        username = f"@{req.username}" if req.username else "(no username)"
        response_lines.append(
            f"{i+1}. {hitalic(time_str)}: User {req.user_id} {username} запросил ссылку из сообщения {req.link_message_id}"
        )

    await message.answer("\n".join(response_lines), parse_mode=ParseMode.HTML)

@router.message(Command("gettopicid"), F.chat.type == ChatType.PRIVATE)
async def get_topic_id_instruction(message: Message):
    """Инструкция для получения Topic ID."""
    if message.from_user.id != settings.admin_id:
        await message.reply("Эта команда доступна только администратору.")
        return
    await message.answer("Чтобы получить ID топика, перешлите любое сообщение из этого топика мне.")

@router.message(Command("stats"))
async def show_statistics(message: Message):
    """Показывает статистику по сообщениям и пользователям."""
    user_id = message.from_user.id
    logging.info(f"User {user_id} requested /stats")

    # Собираем данные из БД
    total_messages = await db.get_total_message_count()
    total_users = await db.get_total_user_count()
    top_messengers = await db.get_top_users_by_messages(limit=5)
    top_interviewers = await db.get_top_users_by_interviews(limit=5)
    user_stats = await db.get_user_stats(user_id)

    # Формируем текст ответа
    stats_text = [hbold("📊 Статистика Чата:")]
    stats_text.append(f"Всего сообщений: {total_messages}")
    stats_text.append(f"Уникальных пользователей: {total_users}")
    stats_text.append("\n" + hbold("🏆 Топ-5 по сообщениям:"))
    if top_messengers:
        for i, user in enumerate(top_messengers, 1):
            username = f"@{user.username}" if user.username else f"ID: {user.user_id}"
            stats_text.append(f"{i}. {username} - {user.message_count} сообщ.")
    else:
        stats_text.append(hitalic("Пока нет данных..."))

    stats_text.append("\n" + hbold("🥇 Топ-5 по 'собесам' (/addlink):"))
    if top_interviewers:
        for i, user in enumerate(top_interviewers, 1):
            username = f"@{user.username}" if user.username else f"ID: {user.user_id}"
            stats_text.append(f"{i}. {username} - {user.interview_count} собес.")
    else:
        stats_text.append(hitalic("Пока нет данных..."))

    # Статистика запросившего пользователя
    stats_text.append("\n" + hbold("👤 Ваша статистика:"))
    if user_stats:
        stats_text.append(f"Сообщений: {user_stats.message_count}")
        stats_text.append(f"'Собеседований': {user_stats.interview_count}")
    else:
        stats_text.append(hitalic("Вы еще не писали в чате или не добавляли ссылки."))

    await message.reply("\n".join(stats_text), parse_mode=ParseMode.HTML)

@router.message(Command("help"))
async def help_command(message: Message):
    """Отправляет справочное сообщение."""
    # TODO: Добавить актуальный текст справки
    help_text = (
        f"{hbold('ℹ️ Справка по боту')} \n\n"
        f"{hbold('/start')} - Приветственное сообщение\n"
        f"{hbold('/addlink HH:MM текст_анонса ссылка')} - Добавить ссылку с анонсом (в ЛС боту)\n"
        f"   - {hitalic('HH:MM')} - Время события (Московское)\n"
        f"   - {hitalic('текст_анонса')} - Текст для анонса в группе\n"
        f"   - {hitalic('ссылка')} - URL встречи/ресурса\n"
        f"{hbold('/stats')} - Показать статистику чата (в ЛС боту)\n"
        f"{hbold('/help')} - Показать это сообщение\n\n"
        f"Админ-команды:\n"
        f"{hbold('/get_topic_id')} - Получить ID топика (переслать сообщение из топика)"
    )
    await message.reply(help_text, parse_mode=ParseMode.HTML)

# --- Обработка пересланных сообщений (для get_topic_id) --- #