# src/db/models.py
import datetime

from sqlalchemy import (
    create_engine, MetaData, Table, Integer, String, Column, DateTime,
    ForeignKey, BigInteger, Boolean, UniqueConstraint, Text # Используем BigInteger для chat_id/user_id
)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
from sqlalchemy.sql import func # для CURRENT_TIMESTAMP
from typing import Optional

# Базовый класс для декларативных моделей
Base = declarative_base()

class Link(Base):
    """Модель для хранения анонсов и ссылок."""
    __tablename__ = 'links'

    id: Mapped[int] = mapped_column(primary_key=True) # PK
    posted_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True) # ID сообщения в целевом чате
    posted_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)    # ID целевого чата
    link_url: Mapped[str] = mapped_column(String, nullable=False)
    announcement_text: Mapped[str] = mapped_column(String)
    added_by_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    added_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now() # Время добавления
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True # Время последнего обновления
    )
    event_time_str: Mapped[Optional[str]] = mapped_column(String, nullable=True) # Время как ввел пользователь (HH:MM)
    event_time_utc: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True, index=True) # Время события в UTC
    is_active: Mapped[bool] = mapped_column(Boolean, default=True) # Флаг активности ссылки
    pending: Mapped[bool] = mapped_column(Boolean, default=True) # True - если ожидает публикации
    reminder_30_sent: Mapped[bool] = mapped_column(Boolean, default=False, index=True) # Флаг 30-минутного напоминания
    reminder_10_sent: Mapped[bool] = mapped_column(Boolean, default=False, index=True) # Флаг 10-минутного напоминания

    # Связь с запросами (если нужна)
    requests: Mapped[list["Request"]] = relationship(back_populates="link", foreign_keys="[Request.link_id]") # Указываем FK явно

    def __repr__(self):
        return f"<Link(id={self.id}, msg_id={self.posted_message_id}, url='{self.link_url[:20]}...', event_time='{self.event_time_str}', active={self.is_active})>"

class Request(Base):
    """Модель для логирования запросов на получение ссылки."""
    __tablename__ = 'requests'

    id: Mapped[int] = mapped_column(primary_key=True) # PK
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=True) # username может отсутствовать
    requested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now() # Время запроса
    )
    # Добавляем ForeignKey на links.id
    link_id: Mapped[int] = mapped_column(ForeignKey('links.id'), nullable=False, index=True)
    # Делаем ForeignKey на сообщение необязательным
    link_message_id: Mapped[Optional[int]] = mapped_column(ForeignKey('links.posted_message_id'), nullable=True)

    # Связь с ссылкой по link_id
    link: Mapped["Link"] = relationship(foreign_keys=[link_id], back_populates="requests") # Восстанавливаем back_populates

    def __repr__(self):
        return f"<Request(id={self.id}, user_id={self.user_id}, link_id={self.link_id}, link_msg_id={self.link_message_id}, time='{self.requested_at}')>"

class GroupMessage(Base):
    __tablename__ = 'group_messages'

    id: Mapped[int] = mapped_column(primary_key=True) # PK
    message_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[Optional[str]] = mapped_column(String)
    message_text: Mapped[Optional[str]] = mapped_column(String) # Text messages
    # Добавить поля для других типов контента по необходимости (фото, документы и т.д.)
    timestamp: Mapped[datetime.datetime] = mapped_column(default=func.now(), index=True)

    def __repr__(self):
        text_preview = f"'{self.message_text[:30]}..." if self.message_text else "None"
        return f"<GroupMessage(id={self.id}, msg_id={self.message_id}, user_id={self.user_id}, text={text_preview})>"

class UserStats(Base):
    __tablename__ = 'user_stats'

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True) # PK - User ID
    username: Mapped[Optional[str]] = mapped_column(String) # Сохраняем последний известный username
    interview_count: Mapped[int] = mapped_column(default=0)
    message_count: Mapped[int] = mapped_column(default=0) # Можно добавить счетчик сообщений
    first_seen: Mapped[datetime.datetime] = mapped_column(default=func.now())
    last_seen: Mapped[datetime.datetime] = mapped_column(default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<UserStats(user_id={self.user_id}, interviews={self.interview_count}, messages={self.message_count})>"
