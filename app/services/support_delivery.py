from __future__ import annotations

import logging

from aiogram import Bot

from app.bot.keyboards.support import admin_ticket_keyboard, user_reply_keyboard
from app.core.config import Settings
from app.db.models import SupportTicket, User
from app.services.support_tickets import SupportAccessSummary

logger = logging.getLogger(__name__)


class SupportConfigurationError(RuntimeError):
    pass


def support_admin_chat_id(settings: Settings) -> int:
    chat_id = settings.support_admin_chat_id_value
    if chat_id is None:
        logger.error("SUPPORT_ADMIN_CHAT_ID is missing or invalid")
        raise SupportConfigurationError("SUPPORT_ADMIN_CHAT_ID is not configured")
    return chat_id


def admin_is_authorized(
    settings: Settings, *, telegram_id: int, chat_id: int
) -> bool:
    configured_chat_id = settings.support_admin_chat_id_value
    return (
        configured_chat_id is not None
        and chat_id == configured_chat_id
        and settings.is_admin(telegram_id)
    )


def ticket_card(
    ticket: SupportTicket,
    user: User,
    access: SupportAccessSummary,
    text: str,
    *,
    continuation: bool = False,
) -> str:
    username = f"@{user.username}" if user.username else "не указан"
    ends_at = access.ends_at.isoformat() if access.ends_at else "без даты окончания"
    heading = "Новое сообщение AIR" if continuation else "Новое обращение AIR"
    return (
        f"{heading} #{ticket.id}\n\n"
        f"Пользователь:\n{username}\n"
        f"Telegram ID: {user.telegram_id}\n\n"
        f"Имя:\n{user.telegram_first_name}\n\n"
        f"Email:\n{user.receipt_email or 'не указан'}\n\n"
        f"Доступ:\n{access.plan} / {access.status} / {ends_at}\n\n"
        f"Сообщение:\n{text}"
    )


async def send_ticket_to_admin(
    bot: Bot,
    settings: Settings,
    ticket: SupportTicket,
    user: User,
    access: SupportAccessSummary,
    text: str,
    *,
    continuation: bool = False,
) -> None:
    await bot.send_message(
        support_admin_chat_id(settings),
        ticket_card(ticket, user, access, text, continuation=continuation),
        reply_markup=admin_ticket_keyboard(ticket.id),
    )


async def send_admin_reply_to_user(
    bot: Bot, user: User, ticket: SupportTicket, text: str
) -> None:
    await bot.send_message(
        chat_id=user.telegram_id,
        text=f"Ответ поддержки AIR\n\n{text}",
        reply_markup=user_reply_keyboard(ticket.id),
    )
