from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def get_link_keyboard(link_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой 'Получить ссылку'."""
    keyboard = [
        [InlineKeyboardButton(text="🔗 Получить ссылку", callback_data=f"getlink_{link_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)