# src/handlers/links.py
import logging
from typing import Optional, NamedTuple
from aiogram import Bot, Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.formatting import Text
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hlink

# Утилиты, константы и конфигурация
from src.config.config import settings
from src.utils.constants import URL_REGEX, DATE_REGEX, TIME_REGEX
from src.utils.date_parser import parse_datetime_string, DateTimeParseError, PastDateTimeError
from src.utils.callback_data import ChatSelectCallback # Исправлен путь импорта
from src.utils.keyboards import LinkCallbackFactory, get_link_keyboard # Оставляем импорт для клавиатуры ссылки
from src.utils.misc import get_random_phrase
from src.db.models import Link

# Сервисы БД
from src.services.link_service import (
    add_link as db_add_link,
    update_link_message_id as db_update_link_message_id,
    get_link_by_id as db_get_link_by_id
)
from src.services.request_log_service import (
    log_link_request as db_log_link_request
)
from src.services.stats_service import (
    increment_interview_count as db_increment_interview_count
)
from src.services.user_service import add_or_update_user

# --- НОВОЕ: Структура для аргументов и ошибка парсинга --- #
class AddLinkArgs(NamedTuple):
    link_url: str
    date_str: Optional[str]
    time_str: Optional[str]
    announcement_text: str

class ArgumentParsingError(ValueError):
    """Исключение для ошибок во время парсинга аргументов команды."""
    pass
# --- КОНЕЦ НОВОГО --- #

# Загрузка конфигурации
GROUP_CHAT_ID = settings.main_group_id

router = Router()

# --- Вспомогательная функция для парсинга аргументов --- #
def _parse_addlink_args(args_str: Optional[str]) -> AddLinkArgs:
    """Парсит строку аргументов команды /addlink.

    Args:
        args_str: Строка аргументов (command.args).

    Returns:
        AddLinkArgs: Разобранные аргументы.

    Raises:
        ArgumentParsingError: Если парсинг не удался.
    """
    if not args_str:
        raise ArgumentParsingError(
            "Пожалуйста, укажите ссылку после команды.\n"
            "Пример: /addlink https://example.com [ДД.ММ ЧЧ:ММ] [Текст объявления]"
        )

    command_parts = args_str.strip().split()

    link_url: Optional[str] = None
    date_str: Optional[str] = None
    time_str: Optional[str] = None
    announcement_text_parts = []

    current_part_index = 0

    # 1. Ссылка (должна быть первой)
    if current_part_index < len(command_parts) and URL_REGEX.match(command_parts[current_part_index]):
        link_url = command_parts[current_part_index]
        current_part_index += 1
    else:
        raise ArgumentParsingError("Неверный формат ссылки. Ссылка должна начинаться с http:// или https://")

    # 2. Дата (опционально, следующая часть)
    if current_part_index < len(command_parts) and DATE_REGEX.match(command_parts[current_part_index]):
        date_str = command_parts[current_part_index]
        current_part_index += 1

    # 3. Время (опционально, следует за датой ИЛИ если дата не указана, но есть время)
    if current_part_index < len(command_parts) and TIME_REGEX.match(command_parts[current_part_index]):
        is_time_immediately_after_link = (date_str is None and current_part_index == 1)
        is_time_after_date = (date_str is not None and current_part_index == 2)
        if is_time_immediately_after_link or is_time_after_date:
            time_str = command_parts[current_part_index]
            current_part_index += 1

    # 4. Текст объявления (все остальное)
    announcement_text_parts = command_parts[current_part_index:]
    announcement_text = " ".join(announcement_text_parts) if announcement_text_parts else "Анонс"

    # Валидация: если есть дата, должно быть и время, и наоборот
    if (date_str and not time_str) or (not date_str and time_str):
        raise ArgumentParsingError("Для указания времени события необходимо указать и дату, и время (ДД.ММ ЧЧ:ММ). Либо не указывать их вовсе.")

    return AddLinkArgs(
        link_url=link_url,
        date_str=date_str,
        time_str=time_str,
        announcement_text=announcement_text
    )


# --- Вспомогательная функция для отправки анонса в группу --- #
async def _send_announcement_to_group(bot: Bot, link: Link) -> bool:
    """Отправляет анонс ссылки в группу и обновляет message_id в БД.

    Args:
        bot: Экземпляр бота.
        link: Объект Link с данными (включая link.id).

    Returns:
        bool: True, если сообщение успешно отправлено и message_id обновлен в БД,
              False в противном случае.
    """
    group_message_text = f"{link.announcement_text}\n\n" \
                         f"Добавил: [User {link.added_by_user_id}]" # TODO: Получить имя пользователя? Или оставить ID?
                         # f"Добавил: {message.from_user.full_name}" # Имя пользователя недоступно здесь
    if link.event_time_str:
        group_message_text += f"\n📅 Дата и время: {link.event_time_str} МСК"

    keyboard = get_link_keyboard(link.id)

    try:
        sent_message = await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=group_message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        logging.info(f"Sent message for link_id {link.id} to group {GROUP_CHAT_ID}, message_id={sent_message.message_id}")

        # Обновляем message_id в базе данных
        success = await db_update_link_message_id(link.id, sent_message.message_id)
        if success:
            return True
        else:
            # Если не удалось обновить ID в БД - это проблема.
            logging.error(f"Failed to update message_id {sent_message.message_id} for link_id {link.id} in DB.")
            # Попытка удалить некорректное сообщение из группы
            try:
                await bot.delete_message(chat_id=GROUP_CHAT_ID, message_id=sent_message.message_id)
                logging.warning(f"Deleted group message {sent_message.message_id} due to DB update failure.")
            except Exception as del_err:
                logging.error(f"Failed to delete message {sent_message.message_id} from group {GROUP_CHAT_ID} after DB update failure: {del_err}")
            return False # Сигнализируем об ошибке

    except TelegramBadRequest as e:
        logging.error(f"Telegram error sending link message to group {GROUP_CHAT_ID} for link {link.id}: {e}")
        return False
    except Exception as e:
        logging.exception(f"Unexpected error sending link message to group {GROUP_CHAT_ID} for link {link.id}: {e}")
        return False


# --- Вспомогательная функция для отправки ссылки пользователю --- #
async def _send_link_to_user(bot: Bot, user_id: int, link_url: str, link_id: int) -> tuple[bool, str]:
    """Отправляет ссылку личным сообщением пользователю.

    Args:
        bot: Экземпляр бота.
        user_id: ID пользователя, которому отправляем.
        link_url: URL ссылки для отправки.
        link_id: ID ссылки (для логирования).

    Returns:
        tuple[bool, str]: Кортеж (success: bool, message: str).
                        success=True, message="Ссылка отправлена..."
                        success=False, message="Ошибка: Не могу отправить..."
    """
    # Получаем случайную фразу
    random_phrase = get_random_phrase()
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"{random_phrase}\n{link_url}",
            disable_web_page_preview=False # Включаем превью для ЛС
        )
        logging.info(f"Sent link {link_id} to user {user_id}")
        return True, "Ссылка отправлена вам в личные сообщения!"
    except TelegramBadRequest as e:
        if "bot was blocked by the user" in str(e) or "user not found" in str(e) or "chat not found" in str(e):
            logging.warning(f"Cannot send link {link_id} to user {user_id}: Bot blocked or chat not started.")
            return False, "Не могу отправить вам ссылку. Пожалуйста, начните диалог со мной (напишите /start) и попробуйте снова."
        else:
            logging.error(f"Telegram error sending link {link_id} to user {user_id}: {e}")
            return False, "Произошла ошибка при отправке ссылки."
    except Exception as e:
        logging.exception(f"Unexpected error sending link {link_id} to user {user_id}: {e}")
        return False, "Произошла непредвиденная ошибка."


# --- Обработчик команды добавления ссылки --- #

@router.message(Command("addlink"))
async def add_link(message: Message, command: CommandObject, bot: Bot):
    """Обработчик команды /addlink."""
    # --- Парсинг аргументов вынесен --- #
    try:
        parsed_args = _parse_addlink_args(command.args)
    except ArgumentParsingError as e:
        await message.answer(str(e))
        return

    # --- Использование разобранных аргументов --- #
    link_url = parsed_args.link_url
    date_str = parsed_args.date_str
    time_str = parsed_args.time_str
    announcement_text = parsed_args.announcement_text

    # --- Логика обработки даты/времени --- #
    event_time_utc = None
    event_time_str = None
    if date_str and time_str: # Проверка уже сделана в парсере
        try:
            event_time_utc = parse_datetime_string(date_str, time_str)
            event_time_str = f"{date_str} {time_str}"
        except DateTimeParseError:
            await message.answer("Неверный формат даты или времени. Используйте ДД.ММ(.ГГГГ) и ЧЧ:ММ.")
            return
        except PastDateTimeError:
            await message.answer("Дата и время события не могут быть в прошлом.")
            return
        except Exception as e:
            logging.error(f"Error parsing date/time '{date_str} {time_str}': {e}")
            await message.answer("Произошла ошибка при обработке даты и времени.")
            return

    # --- Взаимодействие с БД --- #
    added_link = await db_add_link(
        message_id=None, # message_id добавим после отправки в группу
        link_url=link_url,
        announcement_text=announcement_text,
        added_by_user_id=message.from_user.id,
        event_time_str=event_time_str,
        event_time_utc=event_time_utc
    )

    if not added_link or added_link.id is None:
        await message.answer("Не удалось сохранить ссылку. Попробуйте позже.")
        return

    # --- Отправка сообщения в группу вынесена --- #
    send_success = await _send_announcement_to_group(bot, added_link)

    if send_success:
        await message.reply(
            f"Ссылка успешно добавлена и отправлена в группу! "
            f"{f'Напоминание установлено на {event_time_str} МСК.' if event_time_str else ''}"
        )
    else:
        # Сообщение пользователю об ошибке
        # Текст ошибки зависит от того, что вернула _send_announcement_to_group
        # Сейчас она просто возвращает False, нужна более детальная обработка или логи
        await message.reply(
            "Произошла ошибка при отправке сообщения в группу или обновлении записи в БД. "
            "Ссылка сохранена, но анонс в группе может отсутствовать или быть некорректным. "
            "Свяжитесь с администратором."
            # Альтернатива: попытаться удалить added_link из БД, если отправка не удалась?
        )


# --- Обработчик нажатия кнопки "Получить ссылку" --- #

@router.callback_query(LinkCallbackFactory.filter(F.action == "get"))
async def get_link(query: CallbackQuery, callback_data: LinkCallbackFactory, bot: Bot):
    """Обработчик нажатия кнопки получения ссылки."""
    link_id = callback_data.link_id
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.full_name

    logging.info(f"User {user_id} ({username}) requested link_id {link_id}")

    # Логируем запрос в БД и обновляем статистику
    await db_log_link_request(user_id, username, link_id)
    await db_increment_interview_count(user_id, username)

    # Получаем ссылку из БД
    link_record = await db_get_link_by_id(link_id)

    if link_record:
        # --- Отправка ссылки вынесена --- #
        send_success, message_text = await _send_link_to_user(bot, user_id, link_record.link_url, link_id)

        # Отвечаем на колбек
        await query.answer(text=message_text, show_alert=not send_success) # Показываем alert при ошибке

    else:
        logging.warning(f"User {user_id} requested non-existent link_id {link_id}")
        await query.answer(text="Извините, эта ссылка больше не доступна.", show_alert=True)


# --- Обработчик команды добавления ссылки --- #

@router.message(Command("addlink"))
async def handle_add_link(message: Message, command: Optional[CommandObject] = None, bot: Optional[Bot] = None):
    """Обрабатывает команду /addlink или пересылку сообщения для добавления ссылки.
    Создает 'pending' ссылку и отправляет пользователю клавиатуру для выбора чата публикации.
    """
    if not message.from_user:
        logger.warning("Received /addlink command without user info.")
        return

    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    logger.info(f"Handling link add request from user {user_id} ({username or first_name})")

    link_url: Optional[str] = None
    raw_text: Optional[str] = None

    if message.text:
        link_url_match = URL_REGEX.search(message.text)
        link_url = link_url_match.group(0) if link_url_match else None
        raw_text = message.text # Весь текст для дальнейшего парсинга времени и описания
    elif message.forward_from or message.forward_from_chat:
        if message.forward_from:
            logger.info(f"Received forwarded message from user {message.forward_from.id}")
        elif message.forward_from_chat:
            logger.info(f"Received forwarded message from chat {message.forward_from_chat.id}")
        if message.forward_date:
            logger.info(f"Forwarded message date: {message.forward_date}")
        if message.text:
            link_url_match = URL_REGEX.search(message.text)
            link_url = link_url_match.group(0) if link_url_match else None
            raw_text = message.text # Весь текст для дальнейшего парсинга времени и описания

    if not link_url:
        logger.warning(f"No link found in message from user {message.from_user.id}")
        await message.reply("Не удалось найти ссылку в вашем сообщении.")
        return

    # Извлекаем время и описание
    event_time_str: Optional[str] = None
    event_time_utc: Optional[datetime] = None
    announcement_text: str = link_url # По умолчанию текст - это сама ссылка

    if raw_text:
        time_match = TIME_REGEX.search(raw_text)
        if time_match:
            event_time_str = time_match.group(0)
            announcement_text = raw_text.replace(time_match.group(0), "").replace(link_url, "").strip()
            if not announcement_text: # Если после удаления времени и ссылки ничего не осталось
                announcement_text = link_url
        else:
            # Если времени нет, удаляем только ссылку для получения текста
            announcement_text = raw_text.replace(link_url, "").strip()
            if not announcement_text:
                announcement_text = link_url

    # Добавляем ссылку в базу как 'pending'
    pending_link = await db_add_link(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        link_url=link_url,
        event_time_str=event_time_str,
        event_time_utc=event_time_utc,
        announcement_text=announcement_text
    )

    if not pending_link or not pending_link.id:
        logger.error(f"Failed to create pending link for URL: {link_url} by user {user_id}")
        await message.reply("Произошла ошибка при сохранении ссылки. Попробуйте позже.")
        return

    link_id = pending_link.id
    logger.info(f"Created pending link ID: {link_id} for user {user_id}. URL: {link_url}")

    # Формируем клавиатуру для выбора чата
    target_chats = settings.announcement_target_chats
    if not target_chats:
        logger.warning(f"No target chats configured for announcements. Link ID {link_id} remains pending.")
        await message.reply(f"Ссылка {hlink('сохранена', link_url)}, но нет настроенных чатов для публикации. Обратитесь к администратору.")
        return

    builder = InlineKeyboardBuilder()
    for chat in target_chats:
        builder.button(
            text=chat.name,
            callback_data=ChatSelectCallback(link_id=link_id, target_chat_id=chat.id)
        )
    # Можно добавить кнопку отмены?
    # builder.button(text="Отмена", callback_data=ChatSelectCallback(action="cancel", link_id=link_id))
    builder.adjust(1) # По одной кнопке в ряду

    # Отправляем сообщение пользователю с клавиатурой
    await message.reply(
        f"Куда опубликовать анонс для ссылки: {hlink(announcement_text or link_url, link_url)}?",
        reply_markup=builder.as_markup()
    )
