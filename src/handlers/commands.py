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
DATE_REGEX = re.compile(r"^(\d{1,2}[.\s]\d{1,2}(?:[.\s]\d{2,4})?)$")
STRICT_TIME_REGEX = re.compile(r"^(\d{1,2}:\d{2})$")

@router.message(CommandStart())
async def send_welcome(message: Message):
    """Обработчик команды /start."""
    if message.from_user.id == settings.admin_id:
        await message.answer(f"Привет, {hbold('Администратор')}!\n"
                             f"Я бот для анонса ссылок на конференции.\n"
                             f"Добавить новую ссылку: `/addlink [&lt;дата&gt;] &lt;время&gt; [&lt;текст_анонса&gt;] &lt;ссылка&gt;`\n"
                             f"Посмотреть запросы: `/showrequests`\n"
                             f"Узнать Topic ID: `/gettopicid`")
    else:
        await message.answer("Привет! Я бот для анонса ссылок на конференции.\n"
                             "Ты можешь добавить ссылку командой `/addlink` в личных сообщениях со мной.")

@router.message(Command("addlink"), F.chat.type == ChatType.PRIVATE)
async def add_link(message: Message, bot: Bot):
    """Обрабатывает команду /addlink [<дата>] <время> [<текст_анонса>] <ссылка>"""
    if not message.text:
        await message.reply("Пустое сообщение.")
        return

    command_parts = message.text.split() # Разделяем по пробелам
    usage_text = (
        "Неверный формат команды. Использование:\n"
        f"<code>/addlink [&lt;дата&gt;] &lt;время&gt; [&lt;текст_анонса&gt;] &lt;ссылка&gt;</code>\n"
        f"Пример 1 (сегодня/завтра): <code>/addlink 15:00 Созвон https://t.me/joinchat/123</code>\n"
        f"Пример 2 (с датой): <code>/addlink 25.12 18:00 Новогодний созвон https://telemost.yandex.ru/j/456</code>\n"
        f"Пример 3 (с датой и годом): <code>/addlink 01.01.2025 10:00 Утренний созвон https://meet.google.com/abc-def</code>\n"
        f"Дата (опционально) указывается в формате {hcode('ДД.ММ')} или {hcode('ДД.ММ.ГГГГ')}. "
        f"Время указывается по {hbold('Москве')} в формате {hcode('ЧЧ:ММ')}.\n"
        f"Текст анонса (опционально) идет между временем и ссылкой.\n"
        f"Ссылка должна быть {hbold('последним')} аргументом."
    )

    # Проверяем минимальную длину: /addlink <время> <ссылка> (самый короткий вариант)
    if len(command_parts) < 3:
        await message.reply(usage_text, parse_mode=ParseMode.HTML)
        return

    # 1. Парсим команду
    date_str: Optional[str] = None
    time_str: Optional[str] = None
    announcement_text: str = ""
    link_url: Optional[str] = None
    start_index_for_text = 2 # Индекс, с которого начинается текст анонса

    # Проверяем, является ли второй аргумент датой
    if DATE_REGEX.match(command_parts[1]):
        date_str = command_parts[1]
        if len(command_parts) < 4: # Нужно /addlink <дата> <время> <ссылка>
            await message.reply(usage_text, parse_mode=ParseMode.HTML)
            return
        if STRICT_TIME_REGEX.match(command_parts[2]):
            time_str = command_parts[2]
            link_url = command_parts[-1]
            start_index_for_text = 3
            announcement_text = " ".join(command_parts[start_index_for_text:-1]).strip()
        else:
            await message.reply("Неверный формат времени после даты. " + usage_text, parse_mode=ParseMode.HTML)
            return
    # Если второй аргумент не дата, проверяем, является ли он временем
    elif STRICT_TIME_REGEX.match(command_parts[1]):
        time_str = command_parts[1]
        link_url = command_parts[-1]
        start_index_for_text = 2
        announcement_text = " ".join(command_parts[start_index_for_text:-1]).strip()
    else:
        # Если второй аргумент ни дата, ни время - ошибка
        await message.reply("Не найдены дата или время после /addlink. " + usage_text, parse_mode=ParseMode.HTML)
        return

    if not time_str:
        # Эта проверка на всякий случай, логика выше должна гарантировать, что time_str установлен
        await message.reply("Не удалось распознать время. " + usage_text, parse_mode=ParseMode.HTML)
        return

    if not link_url or not (link_url.startswith("http://") or link_url.startswith("https://") or link_url.startswith("t.me/")):
        await message.reply("Последний аргумент не похож на ссылку. Ссылка должна начинаться с http://, https:// или t.me/. " + usage_text, parse_mode=ParseMode.HTML)
        return

    # 2. Обработка даты и времени
    try:
        parsed_time = datetime.datetime.strptime(time_str, "%H:%M").time()
        now_moscow = datetime.datetime.now(MOSCOW_TZ)
        target_date_moscow = now_moscow.date() # По умолчанию - сегодня

        if date_str:
            # Пытаемся распарсить дату
            date_str_normalized = date_str.replace(" ", ".") # Заменяем пробелы на точки
            try:
                parsed_date = datetime.datetime.strptime(date_str_normalized, "%d.%m").date()
                # Если указан только день и месяц, берем текущий год
                target_date_moscow = parsed_date.replace(year=now_moscow.year)
                # Если получившаяся дата уже прошла в этом году, считаем, что это следующий год
                # (например, вводим 01.01, когда сейчас 02.01)
                temp_dt = now_moscow.replace(month=target_date_moscow.month, day=target_date_moscow.day, hour=0, minute=0, second=0, microsecond=0)
                if temp_dt < now_moscow.replace(hour=0, minute=0, second=0, microsecond=0): # Сравниваем только даты
                    target_date_moscow = target_date_moscow.replace(year=now_moscow.year + 1)
                    logging.info(f"Parsed date {date_str} assumed for next year ({target_date_moscow.year}).")
            except ValueError:
                try:
                    # Пробуем парсить с годом (ДД.ММ.ГГГГ или ДД.ММ.ГГ)
                    parsed_date = datetime.datetime.strptime(date_str_normalized, "%d.%m.%Y").date()
                    target_date_moscow = parsed_date
                except ValueError:
                     try:
                        parsed_date = datetime.datetime.strptime(date_str_normalized, "%d.%m.%y").date()
                        target_date_moscow = parsed_date
                     except ValueError:
                        await message.reply(f"Не удалось распознать дату: {hcode(date_str)}. Используйте формат ДД.ММ или ДД.ММ.ГГГГ.", parse_mode=ParseMode.HTML)
                        return
            logging.info(f"Using specified date: {target_date_moscow.strftime('%Y-%m-%d')} MSK")

        # Создаем datetime с вычисленной датой и указанным временем в МСК
        event_dt_moscow = MOSCOW_TZ.localize(
            datetime.datetime.combine(target_date_moscow, parsed_time)
        )

        # Если дата НЕ была указана И время сегодня уже прошло, считаем, что это на завтра
        if not date_str and event_dt_moscow <= now_moscow:
            target_date_moscow += datetime.timedelta(days=1)
            event_dt_moscow = MOSCOW_TZ.localize(
                datetime.datetime.combine(target_date_moscow, parsed_time)
            )
            logging.info(f"Event time {time_str} MSK is for tomorrow ({target_date_moscow.strftime('%Y-%m-%d')}).")
        elif event_dt_moscow <= now_moscow:
             # Если дата была указана, но она в прошлом
             await message.reply(f"Указанная дата и время ({event_dt_moscow.strftime('%d.%m.%Y %H:%M')}) уже прошли.")
             return

        event_dt_utc = event_dt_moscow.astimezone(pytz.utc)
        logging.info(f"Parsed command: Date='{date_str}', Time='{time_str}', Text='{announcement_text}', Link='{link_url}'")
        logging.info(f"Calculated event time: {event_dt_moscow} MSK -> {event_dt_utc} UTC")

    except ValueError as e:
        logging.error(f"Error parsing date/time string ('{date_str}'/'{time_str}'): {e}")
        await message.reply("Произошла ошибка при обработке даты или времени. Убедитесь, что формат верный.")
        return
    except Exception as e:
        logging.exception(f"Unexpected error processing date/time ('{date_str}'/'{time_str}'): {e}")
        await message.reply("Произошла внутренняя ошибка при обработке даты и времени.")
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
        # Если в тексте анонса есть ссылка телемоста, удаляем её
        # Если текста анонса нет, оставляем пустым
        public_announcement_text = re.sub(telemost_pattern, '', announcement_text).strip()

        # Если после удаления телемоста текст пуст И исходный текст был пуст,
        # используем текст по умолчанию
        if not public_announcement_text and not announcement_text:
             public_announcement_text = "Ссылка на созвон"
        elif not public_announcement_text and announcement_text: # Если был текст, но он состоял только из ссылки телемоста
             public_announcement_text = "Ссылка на созвон"

        event_time_formatted = event_dt_moscow.strftime("%d.%m.%Y %H:%M")

        announcement_final_text = (
            f"📢 {hbold('Анонс!')}\n\n"
            f"{hbold(public_announcement_text)}\n\n"
            f"📅 {event_time_formatted} {hbold('МСК')}\n\n"
            f"#анонс #{public_announcement_text.replace(' ', '_').lower()}"
            # f"ID: {new_link.id}" # Можно добавить ID для отладки
        )
        # Старый формат тегов:
        # tags = f"{ZERO_WIDTH_SPACE}#анонс {ZERO_WIDTH_SPACE}#ссылка"
        # announcement_final_text = f"{base_text}\n{tags}"

        keyboard = get_link_keyboard(link_id=new_link.id) # Используем хелпер

        # 5. Отправка анонса в группу
        announcement_msg = await bot.send_message(
            chat_id=settings.main_group_id, # ИСПОЛЬЗУЕМ settings
            text=announcement_final_text,
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
    # Убрал упоминание /getlink, т.к. теперь кнопка
    help_text = (
        f"{hbold('Основные команды:')}\n"
        f"{hcode('/addlink [ДД.ММ] ЧЧ:ММ [текст] ссылка')} - Добавить ссылку с анонсом (в ЛС боту)\n"
        f"   - {hitalic('[ДД.ММ]')} - Опциональная дата (иначе сегодня/завтра)\n"
        f"   - {hitalic('ЧЧ:ММ')} - Время по Москве\n"
        f"   - {hitalic('[текст]')} - Опциональный текст для анонса\n"
        f"   - {hitalic('ссылка')} - Ссылка на встречу (последний аргумент)\n"
        f"{hcode('/showlinks')} - Показать активные ссылки/анонсы\n"
        f"{hcode('/dellink <ID>')} - Деактивировать ссылку/анонс по ID (из /showlinks)\n"
        f"{hcode('/ping')} - Проверить, работает ли бот\n"
        f"{hcode('/help')} - Показать это сообщение\n\n"
        f"{hbold('Как работает:')}\n"
        f"1. Добавляете ссылку через {hcode('/addlink')} боту в личные сообщения.\n"
        f"2. Бот публикует анонс в основной группе ({hcode(str(settings.main_group_id))}) в нужном топике.\n"
        f"3. В анонсе есть кнопка {hbold('Получить ссылку')}, по нажатию на которую бот пришлет ссылку в ЛС.\n"
        f"4. Бот автоматически отправит напоминания в группу за 30 и 10 минут до указанного времени.\n"
        f"5. Команда {hcode('/dellink')} убирает анонс из списка {hcode('/showlinks')} и отменяет будущие напоминания."
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)

# --- Обработка пересланных сообщений (для get_topic_id) --- #