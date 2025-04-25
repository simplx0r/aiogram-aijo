# src/handlers/links.py
import logging
from typing import Optional
from aiogram import Bot, Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

# Утилиты, константы и конфигурация
from src.config import load_config
from src.utils.date_parser import parse_datetime_string, DateTimeParseError, PastDateTimeError
from src.utils.keyboards import LinkCallbackFactory, get_link_keyboard
from src.utils.constants import URL_REGEX, DATE_REGEX, TIME_REGEX

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

# Загрузка конфигурации
config = load_config()
GROUP_CHAT_ID = config.tg_bot.group_chat_id

router = Router()

# --- Обработчик команды добавления ссылки --- #

@router.message(Command("addlink"))
async def add_link(message: Message, command: CommandObject, bot: Bot):
    """Обработчик команды /addlink."""
    if not command.args:
        await message.answer(
            "Пожалуйста, укажите ссылку после команды.\n"
            "Пример: /addlink https://example.com [ДД.ММ ЧЧ:ММ] [Текст объявления]"
        )
        return

    args_str = command.args.strip()
    command_parts = args_str.split()

    link_url: Optional[str] = None
    date_str: Optional[str] = None
    time_str: Optional[str] = None
    announcement_text_parts = []

    # Пытаемся извлечь ссылку, дату и время
    current_part_index = 0

    # 1. Ссылка (должна быть первой)
    if URL_REGEX.match(command_parts[current_part_index]):
        link_url = command_parts[current_part_index]
        current_part_index += 1
    else:
        await message.answer("Неверный формат ссылки. Ссылка должна начинаться с http:// или https://")
        return

    # 2. Дата (опционально, следующая часть)
    if current_part_index < len(command_parts) and DATE_REGEX.match(command_parts[current_part_index]):
        date_str = command_parts[current_part_index]
        current_part_index += 1

    # 3. Время (опционально, следует за датой ИЛИ если дата не указана, но есть время)
    if current_part_index < len(command_parts) and TIME_REGEX.match(command_parts[current_part_index]):
        # Время может идти сразу после ссылки, если нет даты
        if date_str is None and current_part_index == 1:
             time_str = command_parts[current_part_index]
             current_part_index += 1
        # Время идет после даты
        elif date_str is not None and current_part_index == 2:
             time_str = command_parts[current_part_index]
             current_part_index += 1
        # Иначе - это не время, а часть текста

    # 4. Текст объявления (все остальное)
    announcement_text_parts = command_parts[current_part_index:]
    announcement_text = " ".join(announcement_text_parts) if announcement_text_parts else "Анонс"

    # Валидация: если есть дата, должно быть и время, и наоборот
    if (date_str and not time_str) or (not date_str and time_str):
        await message.answer("Для указания времени события необходимо указать и дату, и время (ДД.ММ ЧЧ:ММ). Либо не указывать их вовсе.")
        return

    event_time_utc = None
    event_time_str = None
    if date_str and time_str:
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

    # --- Отправка сообщения в группу --- #
    group_message_text = f"{added_link.announcement_text}\n\n" \
                         f"Добавил: {message.from_user.full_name}"
    if added_link.event_time_str:
        group_message_text += f"\n📅 Дата и время: {added_link.event_time_str} МСК"

    keyboard = get_link_keyboard(added_link.id)

    try:
        sent_message = await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=group_message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True # Отключаем превью ссылки
        )
        logging.info(f"Sent message for link_id {added_link.id} to group {GROUP_CHAT_ID}, message_id={sent_message.message_id}")

        # Обновляем message_id в базе данных
        success = await db_update_link_message_id(added_link.id, sent_message.message_id)
        if success:
            await message.reply(
                f"Ссылка успешно добавлена и отправлена в группу! "
                f"{f'Напоминание установлено на {event_time_str} МСК.' if event_time_str else ''}"
            )
        else:
            # Если не удалось обновить ID, это проблема, но пользователю уже ответили успехом о добавлении.
            # Нужно логировать и, возможно, пытаться исправить вручную или удалить сообщение из группы.
            logging.error(f"Failed to update message_id {sent_message.message_id} for link_id {added_link.id} in DB.")
            # Можно попробовать удалить сообщение из группы
            try:
                await bot.delete_message(chat_id=GROUP_CHAT_ID, message_id=sent_message.message_id)
                await message.reply("Произошла ошибка при сохранении ID сообщения. Запись удалена из группы. Попробуйте добавить ссылку снова.")
            except Exception as del_err:
                logging.error(f"Failed to delete message {sent_message.message_id} from group {GROUP_CHAT_ID} after DB update failure: {del_err}")
                await message.reply("Произошла ошибка при сохранении ID сообщения. Запись в группе могла остаться. Свяжитесь с администратором.")

    except TelegramBadRequest as e:
        logging.error(f"Telegram error sending link message to group {GROUP_CHAT_ID}: {e}")
        # TODO: Попытаться удалить запись из БД, если не удалось отправить в группу?
        await message.reply("Ошибка при отправке сообщения в группу. Возможно, у бота нет прав или чат не найден.")
    except Exception as e:
        logging.exception(f"Unexpected error sending link message to group {GROUP_CHAT_ID}: {e}")
        await message.reply("Произошла непредвиденная ошибка при отправке в группу.")

# --- Обработчик нажатия кнопки "Получить ссылку" --- #

@router.callback_query(LinkCallbackFactory.filter(F.action == "get"))
async def get_link(query: CallbackQuery, callback_data: LinkCallbackFactory, bot: Bot):
    """Обработчик нажатия кнопки получения ссылки."""
    link_id = callback_data.link_id
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.full_name

    logging.info(f"User {user_id} ({username}) requested link_id {link_id}")

    # Логируем запрос в БД
    await db_log_link_request(user_id, username, link_id)
    await db_increment_interview_count(user_id, username)

    # Получаем ссылку из БД
    link_record = await db_get_link_by_id(link_id)

    if link_record:
        try:
            # Отправляем ссылку личным сообщением
            await bot.send_message(
                chat_id=user_id,
                text=f"Держи ссылку:\n{link_record.link_url}",
                disable_web_page_preview=False # Включаем превью для ЛС
            )
            # Отвечаем на колбек, чтобы кнопка перестала "грузиться"
            await query.answer(text="Ссылка отправлена вам в личные сообщения!", show_alert=False)
            logging.info(f"Sent link {link_id} to user {user_id}")
        except TelegramBadRequest as e:
            # Частая ошибка - пользователь не начал диалог с ботом
            if "bot was blocked by the user" in str(e) or "user not found" in str(e) or "chat not found" in str(e):
                logging.warning(f"Cannot send link {link_id} to user {user_id}: Bot blocked or chat not started.")
                await query.answer(text="Не могу отправить вам ссылку. Пожалуйста, начните диалог со мной (напишите /start) и попробуйте снова.", show_alert=True)
            else:
                logging.error(f"Telegram error sending link {link_id} to user {user_id}: {e}")
                await query.answer(text="Произошла ошибка при отправке ссылки.", show_alert=True)
        except Exception as e:
            logging.exception(f"Unexpected error sending link {link_id} to user {user_id}: {e}")
            await query.answer(text="Произошла непредвиденная ошибка.", show_alert=True)
    else:
        logging.warning(f"User {user_id} requested non-existent link_id {link_id}")
        await query.answer(text="Извините, эта ссылка больше не доступна.", show_alert=True)
