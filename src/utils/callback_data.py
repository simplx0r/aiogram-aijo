# src/utils/callback_data.py
from aiogram.filters.callback_data import CallbackData


class LinkCallback(CallbackData, prefix="link"):
    action: str # 'get' или другие действия со ссылкой
    link_id: int


class ChatSelectCallback(CallbackData, prefix="publish"):
    """Callback data для выбора чата для публикации анонса."""
    link_id: int      # ID ссылки, которую публикуем
    target_chat_id: int # ID чата, куда публикуем


class LinkCallbackFactory(CallbackData, prefix="link_action"):
    """CallbackData для действий со ссылкой (например, в анонсе)."""
    action: str # Например, "get", "publish", "delete"
    link_id: int
