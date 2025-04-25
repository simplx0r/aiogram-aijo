# src/handlers/stats.py
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

# Сервисы БД
from src.services.stats_service import (
    get_user_stats as db_get_user_stats,
    get_top_users_by_messages,
    get_top_users_by_interviews
)

router = Router()

# --- Обработчики команд статистики --- #

@router.message(Command("mystats"))
async def my_stats_command(message: Message):
    """Обработчик команды /mystats."""
    user_id = message.from_user.id
    user_stats = await db_get_user_stats(user_id)

    if user_stats:
        await message.answer(
            f"Ваша статистика:\n"
            f" - Сообщений в группе: {user_stats.message_count}\n"
            f" - Запросов ссылок (собеседований): {user_stats.interview_count}\n"
            f" - Первое сообщение: {user_stats.first_message_timestamp.strftime('%Y-%m-%d %H:%M') if user_stats.first_message_timestamp else 'Нет данных'}\n"
            f" - Последняя активность: {user_stats.last_message_timestamp.strftime('%Y-%m-%d %H:%M') if user_stats.last_message_timestamp else 'Нет данных'}"
        )
    else:
        await message.answer("Не найдено статистики для вас. Возможно, вы еще не писали в группе или не запрашивали ссылки.")

@router.message(Command("topmsg"))
async def top_messages_command(message: Message):
    """Обработчик команды /topmsg."""
    top_users = await get_top_users_by_messages(limit=10) # Возьмем топ-10
    if top_users:
        response_text = "Топ пользователей по количеству сообщений:\n\n"
        for i, user in enumerate(top_users, 1):
            username = user.username or f"User ID: {user.user_id}"
            response_text += f"{i}. {username}: {user.message_count}\n"
        await message.answer(response_text)
    else:
        await message.answer("Пока нет данных для статистики.")

@router.message(Command("topinterviews"))
async def top_interviews_command(message: Message):
    """Обработчик команды /topinterviews."""
    top_users = await get_top_users_by_interviews(limit=10) # Возьмем топ-10
    if top_users:
        response_text = "Топ пользователей по количеству запросов ссылок (интервью):\n\n"
        for i, user in enumerate(top_users, 1):
            username = user.username or f"User ID: {user.user_id}"
            response_text += f"{i}. {username}: {user.interview_count}\n"
        await message.answer(response_text)
    else:
        await message.answer("Пока нет данных для статистики.")
