from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import (
    Subscription,
    SupportMessage,
    SupportSenderType,
    SupportTicket,
    SupportTicketStatus,
    User,
)


@dataclass(frozen=True)
class SupportAccessSummary:
    plan: str
    status: str
    ends_at: datetime | None


class SupportTicketService:
    async def active_ticket(
        self, session: AsyncSession, user_id: int
    ) -> SupportTicket | None:
        return await session.scalar(
            select(SupportTicket)
            .where(
                SupportTicket.user_id == user_id,
                SupportTicket.active_marker.is_(True),
                SupportTicket.status.in_(
                    [SupportTicketStatus.OPEN, SupportTicketStatus.ANSWERED]
                ),
            )
            .order_by(SupportTicket.id.desc())
        )

    async def create_ticket(
        self, session: AsyncSession, user_id: int
    ) -> SupportTicket:
        ticket = SupportTicket(
            user_id=user_id,
            status=SupportTicketStatus.OPEN,
            active_marker=True,
        )
        session.add(ticket)
        await session.flush()
        return ticket

    async def get_active_ticket(
        self, session: AsyncSession, ticket_id: int
    ) -> SupportTicket | None:
        ticket = await session.get(SupportTicket, ticket_id)
        if (
            ticket is None
            or ticket.status == SupportTicketStatus.CLOSED
            or ticket.active_marker is not True
        ):
            return None
        return ticket

    async def add_message(
        self,
        session: AsyncSession,
        ticket: SupportTicket,
        sender_type: SupportSenderType,
        text: str,
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
    ) -> SupportMessage:
        message = SupportMessage(
            ticket_id=ticket.id,
            sender_type=sender_type,
            text=text,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
        )
        session.add(message)
        ticket.updated_at = datetime.now(timezone.utc)
        if sender_type == SupportSenderType.ADMIN:
            ticket.status = SupportTicketStatus.ANSWERED
        else:
            ticket.status = SupportTicketStatus.OPEN
        await session.flush()
        return message

    async def message_by_telegram_source(
        self,
        session: AsyncSession,
        telegram_chat_id: int,
        telegram_message_id: int,
    ) -> SupportMessage | None:
        return await session.scalar(
            select(SupportMessage).where(
                SupportMessage.telegram_chat_id == telegram_chat_id,
                SupportMessage.telegram_message_id == telegram_message_id,
            )
        )

    async def close_ticket(
        self, session: AsyncSession, ticket: SupportTicket
    ) -> None:
        now = datetime.now(timezone.utc)
        ticket.status = SupportTicketStatus.CLOSED
        ticket.active_marker = None
        ticket.closed_at = now
        ticket.updated_at = now
        await session.flush()

    async def access_summary(
        self, session: AsyncSession, user: User, settings: Settings
    ) -> SupportAccessSummary:
        if settings.is_program_dev(user.telegram_id):
            return SupportAccessSummary("developer", "active", None)
        if settings.is_tester(user.telegram_id):
            return SupportAccessSummary("tester", "active", None)
        subscription = await session.scalar(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.id.desc())
        )
        if subscription is None:
            return SupportAccessSummary("free", "free", None)
        return SupportAccessSummary(
            subscription.plan,
            subscription.status.value,
            subscription.ends_at,
        )


support_ticket_service = SupportTicketService()
