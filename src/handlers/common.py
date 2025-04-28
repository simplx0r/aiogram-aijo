# src/handlers/common.py
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

# --- Обработчики общих команд --- #

@router.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start."""
    await message.answer(
        "Привет! Я бот для сохранения ссылок и напоминаний о событиях.\n"
        "Используй /addlink &lt;ссылка&gt; [ДД.ММ ЧЧ:ММ] [текст] для добавления.\n"
        "Используй /help для списка всех команд."
    )

@router.message(Command("help"))
async def help_command(message: Message):
    """Обработчик команды /help."""
    # TODO: Дополнить список команд по мере их добавления/реализации
    await message.answer(
        "Доступные команды:\n"
        "/start - Приветственное сообщение\n"
        "/help - Показать это сообщение\n"
        "/addlink &lt;ссылка&gt; &lt;ДД.ММ(.ГГГГ)&gt; &lt;ЧЧ:ММ&gt; [текст объявления] - Добавить ссылку с напоминанием (дата, время и текст опциональны)\n"
        "/mystats - Показать вашу статистику сообщений\n"
        "/topmsg - Показать топ пользователей по сообщениям\n"
        "/topinterviews - Показать топ пользователей по запросам ссылок (интервью)\n"
        # "/showlinks - Показать ваши активные ссылки (TODO)"
        # "/dellink <id> - Удалить ссылку по ID (TODO)"
    )
