from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, ForceReply, Message
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import support as support_handlers
from app.bot.texts.support import SUPPORT_INTRO, SUPPORT_SENT, SUPPORT_UNAVAILABLE
from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    SupportMessage,
    SupportSenderType,
    SupportTicket,
    SupportTicketStatus,
    User,
)
from app.services.support_delivery import (
    SupportConfigurationError,
    admin_is_authorized,
    send_admin_reply_to_user,
    send_ticket_to_admin,
    support_admin_chat_id,
    ticket_card,
)
from app.services.support_tickets import SupportAccessSummary, support_ticket_service


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object | None]] = []

    async def send_message(
        self, chat_id: int, text: str, reply_markup: object | None = None
    ) -> None:
        self.sent.append((chat_id, text, reply_markup))


class FailingBot(FakeBot):
    def __init__(self, forbidden_chat_id: int) -> None:
        super().__init__()
        self.forbidden_chat_id = forbidden_chat_id

    async def send_message(
        self, chat_id: int, text: str, reply_markup: object | None = None
    ) -> None:
        if chat_id == self.forbidden_chat_id:
            raise TelegramForbiddenError(
                method=SendMessage(chat_id=chat_id, text=text),
                message="Forbidden: bot was blocked by the user",
            )
        await super().send_message(chat_id, text, reply_markup)


class FakeApiBot:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def __call__(self, method: object, **_: object) -> object:
        self.calls.append(method)
        if isinstance(method, AnswerCallbackQuery):
            return True
        return True


class FakeState:
    def __init__(self, data: dict[str, object] | None = None) -> None:
        self.data = data or {}
        self.cleared = False

    async def clear(self) -> None:
        self.cleared = True
        self.data = {}

    async def get_data(self) -> dict[str, object]:
        return self.data

    async def set_state(self, state: object) -> None:
        self.data["state"] = state

    async def update_data(self, **data: object) -> None:
        self.data.update(data)


class FakeMessage:
    def __init__(
        self,
        *,
        telegram_id: int,
        first_name: str = "Антон",
        username: str | None = "anton",
        text: str | None = None,
        chat_id: int | None = None,
        chat_type: str = "private",
    ) -> None:
        self.from_user = SimpleNamespace(
            id=telegram_id,
            first_name=first_name,
            username=username,
        )
        self.chat = SimpleNamespace(
            id=chat_id if chat_id is not None else telegram_id,
            type=chat_type,
        )
        self.text = text
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup: object | None = None) -> None:
        self.answers.append((text, reply_markup))


async def make_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'support.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def support_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "support_admin_chat_id": "-100123456789",
        "admin_telegram_ids": "749408538",
    }
    values.update(overrides)
    return Settings(**values)


def admin_callback(
    ticket_id: int,
    *,
    action: str = "admin_reply",
    telegram_id: int = 749408538,
    chat_id: int = -100123456789,
) -> tuple[CallbackQuery, FakeApiBot]:
    bot = FakeApiBot()
    admin = TelegramUser(
        id=telegram_id,
        is_bot=False,
        first_name="Администратор",
    )
    bot_user = TelegramUser(id=8618411820, is_bot=True, first_name="AIR")
    card = Message(
        message_id=10,
        date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type="supergroup", title="AIR Support"),
        from_user=bot_user,
        text=f"Новое обращение AIR #{ticket_id}",
    ).as_(bot)  # type: ignore[arg-type]
    callback = CallbackQuery(
        id="support-callback",
        from_user=admin,
        chat_instance="support-chat",
        message=card,
        data=f"support:{action}:{ticket_id}",
    ).as_(bot)  # type: ignore[arg-type]
    return callback, bot


@pytest.mark.asyncio
async def test_support_command_opens_flow_without_creating_ticket(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    monkeypatch.setattr(support_handlers, "session_factory", sessions)
    monkeypatch.setattr(
        support_handlers, "get_settings", lambda: support_settings()
    )
    message = FakeMessage(telegram_id=1001)
    state = FakeState()

    await support_handlers.support_command(message, state)  # type: ignore[arg-type]

    assert message.answers[0][0] == SUPPORT_INTRO
    assert message.answers[0][1] is not None
    async with sessions() as session:
        assert await session.scalar(select(func.count(SupportTicket.id))) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_start_support_deep_link_still_opens_support_flow(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    monkeypatch.setattr(support_handlers, "session_factory", sessions)
    monkeypatch.setattr(
        support_handlers, "get_settings", lambda: support_settings()
    )
    message = FakeMessage(telegram_id=1007, text="/start support")
    state = FakeState()

    await support_handlers.support_deep_link(message, state)  # type: ignore[arg-type]

    assert message.answers[0][0] == SUPPORT_INTRO
    assert state.cleared is True
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
async def test_support_command_does_not_start_user_flow_in_groups(
    chat_type: str,
) -> None:
    message = FakeMessage(
        telegram_id=1001,
        chat_id=-100123456789,
        chat_type=chat_type,
    )
    state = FakeState()

    await support_handlers.support_command(message, state)  # type: ignore[arg-type]

    assert message.answers == []
    assert state.cleared is False


@pytest.mark.asyncio
async def test_user_message_creates_ticket_saves_it_and_notifies_admin(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    settings = support_settings()
    monkeypatch.setattr(support_handlers, "session_factory", sessions)
    monkeypatch.setattr(support_handlers, "get_settings", lambda: settings)
    message = FakeMessage(
        telegram_id=1002,
        first_name="Мария",
        username="maria",
        text="Не открывается оплата, email maria@example.com",
    )
    state = FakeState({"support_ticket_id": None})
    bot = FakeBot()

    await support_handlers.receive_support_message(  # type: ignore[arg-type]
        message, state, bot
    )

    assert message.answers[-1][0] == SUPPORT_SENT
    assert state.cleared is True
    assert bot.sent[0][0] == -100123456789
    assert "Новое обращение AIR #1" in bot.sent[0][1]
    assert "Telegram ID: 1002" in bot.sent[0][1]
    assert "maria@example.com" in bot.sent[0][1]
    async with sessions() as session:
        ticket = await session.scalar(select(SupportTicket))
        saved_message = await session.scalar(select(SupportMessage))
        assert ticket is not None
        assert ticket.status == SupportTicketStatus.OPEN
        assert saved_message is not None
        assert saved_message.sender_type == SupportSenderType.USER
        assert saved_message.text == message.text
    await engine.dispose()


@pytest.mark.asyncio
async def test_repeated_support_message_continues_the_only_active_ticket(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    monkeypatch.setattr(support_handlers, "session_factory", sessions)
    monkeypatch.setattr(
        support_handlers, "get_settings", lambda: support_settings()
    )
    bot = FakeBot()

    for text in ("Первое сообщение", "Уточнение"):
        message = FakeMessage(telegram_id=1010, text=text)
        await support_handlers.receive_support_message(  # type: ignore[arg-type]
            message, FakeState({"support_ticket_id": None}), bot
        )

    async with sessions() as session:
        assert await session.scalar(select(func.count(SupportTicket.id))) == 1
        assert await session.scalar(select(func.count(SupportMessage.id))) == 2
    assert "Новое обращение AIR #1" in bot.sent[0][1]
    assert "Новое сообщение AIR #1" in bot.sent[1][1]
    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_reply_is_saved_and_delivered_to_correct_user(tmp_path) -> None:
    sessions, engine = await make_sessions(tmp_path)
    bot = FakeBot()
    async with sessions() as session:
        user = User(
            telegram_id=1003,
            telegram_first_name="User",
            motivation="Существующие данные",
        )
        session.add(user)
        await session.flush()
        ticket = await support_ticket_service.create_ticket(session, user.id)
        await support_ticket_service.add_message(
            session, ticket, SupportSenderType.USER, "Вопрос"
        )
        await support_ticket_service.add_message(
            session, ticket, SupportSenderType.ADMIN, "Ответ"
        )
        await send_admin_reply_to_user(bot, user, ticket, "Ответ")  # type: ignore[arg-type]
        await session.commit()

        assert ticket.status == SupportTicketStatus.ANSWERED
        assert bot.sent == [
            (
                1003,
                "Ответ поддержки AIR\n\nОтвет",
                bot.sent[0][2],
            )
        ]
        assert user.motivation == "Существующие данные"
        assert await session.scalar(
            select(func.count(SupportMessage.id)).where(
                SupportMessage.ticket_id == ticket.id
            )
        ) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_admin_reply_flow_keeps_ticket_id_and_uses_telegram_id(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    settings = support_settings()
    monkeypatch.setattr(support_handlers, "session_factory", sessions)
    monkeypatch.setattr(support_handlers, "get_settings", lambda: settings)
    recipient_telegram_id = 987654321
    async with sessions() as session:
        user = User(
            telegram_id=recipient_telegram_id,
            telegram_first_name="Получатель",
        )
        session.add(user)
        await session.flush()
        assert user.id != user.telegram_id
        ticket = await support_ticket_service.create_ticket(session, user.id)
        await support_ticket_service.add_message(
            session, ticket, SupportSenderType.USER, "Вопрос"
        )
        await session.commit()
        ticket_id = ticket.id

    state = FakeState()
    callback, callback_bot = admin_callback(ticket_id)
    await support_handlers.start_admin_reply(  # type: ignore[arg-type]
        callback, state
    )

    assert state.data["support_ticket_id"] == ticket_id
    prompt = next(
        call for call in callback_bot.calls if isinstance(call, SendMessage)
    )
    assert isinstance(prompt.reply_markup, ForceReply)
    assert prompt.reply_markup.selective is False

    admin_message = FakeMessage(
        telegram_id=749408538,
        chat_id=-100123456789,
        chat_type="supergroup",
        text="Проверенный ответ",
    )
    delivery_bot = FakeBot()
    await support_handlers.receive_admin_reply(  # type: ignore[arg-type]
        admin_message, state, delivery_bot
    )

    assert delivery_bot.sent[0][0] == recipient_telegram_id
    assert "Проверенный ответ" in delivery_bot.sent[0][1]
    assert state.cleared is True
    assert admin_message.answers[-1][0] == (
        f"Ответ по обращению #{ticket_id} отправлен."
    )
    async with sessions() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        admin_reply = await session.scalar(
            select(SupportMessage).where(
                SupportMessage.ticket_id == ticket_id,
                SupportMessage.sender_type == SupportSenderType.ADMIN,
            )
        )
        assert ticket is not None
        assert ticket.status == SupportTicketStatus.ANSWERED
        assert admin_reply is not None
        assert admin_reply.text == "Проверенный ответ"
    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_reply_delivery_failure_is_reported_and_not_committed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    settings = support_settings()
    monkeypatch.setattr(support_handlers, "session_factory", sessions)
    monkeypatch.setattr(support_handlers, "get_settings", lambda: settings)
    recipient_telegram_id = 876543210
    async with sessions() as session:
        user = User(
            telegram_id=recipient_telegram_id,
            telegram_first_name="Заблокировал бота",
        )
        session.add(user)
        await session.flush()
        ticket = await support_ticket_service.create_ticket(session, user.id)
        await support_ticket_service.add_message(
            session, ticket, SupportSenderType.USER, "Вопрос"
        )
        await session.commit()
        ticket_id = ticket.id

    state = FakeState({"support_ticket_id": ticket_id})
    admin_message = FakeMessage(
        telegram_id=749408538,
        chat_id=-100123456789,
        chat_type="supergroup",
        text="Ответ, который нельзя доставить",
    )
    await support_handlers.receive_admin_reply(  # type: ignore[arg-type]
        admin_message,
        state,
        FailingBot(recipient_telegram_id),
    )

    assert state.cleared is False
    assert admin_message.answers[-1][0] == "Не удалось доставить ответ пользователю."
    assert f"ticket_id={ticket_id}" in caplog.text
    assert f"telegram_id={recipient_telegram_id}" in caplog.text
    assert "exception_type=TelegramForbiddenError" in caplog.text
    async with sessions() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        admin_messages = await session.scalar(
            select(func.count(SupportMessage.id)).where(
                SupportMessage.ticket_id == ticket_id,
                SupportMessage.sender_type == SupportSenderType.ADMIN,
            )
        )
        assert ticket is not None
        assert ticket.status == SupportTicketStatus.OPEN
        assert admin_messages == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_regular_user_cannot_enter_admin_reply_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        support_handlers, "get_settings", lambda: support_settings()
    )
    callback, callback_bot = admin_callback(
        1,
        telegram_id=999999,
        chat_id=-200987654321,
    )
    state = FakeState()

    await support_handlers.start_admin_reply(  # type: ignore[arg-type]
        callback, state
    )

    assert "support_ticket_id" not in state.data
    answer = next(
        call for call in callback_bot.calls if isinstance(call, AnswerCallbackQuery)
    )
    assert answer.text == "Недостаточно прав"
    assert answer.show_alert is True


@pytest.mark.asyncio
async def test_admin_can_close_ticket_from_support_group(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    monkeypatch.setattr(support_handlers, "session_factory", sessions)
    monkeypatch.setattr(
        support_handlers, "get_settings", lambda: support_settings()
    )
    recipient_telegram_id = 765432109
    async with sessions() as session:
        user = User(
            telegram_id=recipient_telegram_id,
            telegram_first_name="Получатель",
        )
        session.add(user)
        await session.flush()
        ticket = await support_ticket_service.create_ticket(session, user.id)
        await session.commit()
        ticket_id = ticket.id

    callback, callback_bot = admin_callback(ticket_id, action="admin_close")
    state = FakeState()
    delivery_bot = FakeBot()

    await support_handlers.close_support_ticket(  # type: ignore[arg-type]
        callback, state, delivery_bot
    )

    assert state.cleared is True
    assert delivery_bot.sent[0][0] == recipient_telegram_id
    assert any(isinstance(call, AnswerCallbackQuery) for call in callback_bot.calls)
    async with sessions() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        assert ticket is not None
        assert ticket.status == SupportTicketStatus.CLOSED
        assert ticket.closed_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_closed_ticket_rejects_reply_and_allows_new_ticket(tmp_path) -> None:
    sessions, engine = await make_sessions(tmp_path)
    async with sessions() as session:
        user = User(telegram_id=1004, telegram_first_name="User")
        session.add(user)
        await session.flush()
        ticket = await support_ticket_service.create_ticket(session, user.id)
        await support_ticket_service.close_ticket(session, ticket)
        await session.commit()

        assert ticket.status == SupportTicketStatus.CLOSED
        assert ticket.closed_at is not None
        assert await support_ticket_service.get_active_ticket(session, ticket.id) is None
        new_ticket = await support_ticket_service.create_ticket(session, user.id)
        await session.commit()
        assert new_ticket.id != ticket.id
        assert new_ticket.status == SupportTicketStatus.OPEN
    await engine.dispose()


def test_admin_callbacks_require_admin_chat_or_allowlisted_admin() -> None:
    settings = support_settings()
    assert admin_is_authorized(settings, telegram_id=1, chat_id=-100123456789)
    assert admin_is_authorized(settings, telegram_id=749408538, chat_id=123)
    assert not admin_is_authorized(settings, telegram_id=999, chat_id=123)


def test_missing_admin_chat_is_safe_and_logs_configuration_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = support_settings(support_admin_chat_id="")
    with pytest.raises(SupportConfigurationError):
        support_admin_chat_id(settings)
    assert "SUPPORT_ADMIN_CHAT_ID is missing or invalid" in caplog.text


@pytest.mark.asyncio
async def test_missing_admin_chat_returns_calm_user_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        support_handlers,
        "get_settings",
        lambda: support_settings(support_admin_chat_id=""),
    )
    message = FakeMessage(telegram_id=1005)
    await support_handlers.open_support_flow(  # type: ignore[arg-type]
        message, FakeState()
    )
    assert message.answers == [(SUPPORT_UNAVAILABLE, None)]


@pytest.mark.asyncio
async def test_admin_card_and_delivery_exclude_payment_secrets() -> None:
    settings = support_settings()
    ticket = SupportTicket(id=9, user_id=1, status=SupportTicketStatus.OPEN)
    user = User(
        id=1,
        telegram_id=1006,
        telegram_first_name="User",
        username="user",
        receipt_email="user@example.com",
    )
    access = SupportAccessSummary("air_30_days", "active", datetime.now(timezone.utc))
    text = ticket_card(ticket, user, access, "Нужна помощь")
    assert "user@example.com" in text
    for forbidden in ("confirmation_url", "idempotency_key", "initData", "secret"):
        assert forbidden not in text
    bot = FakeBot()
    await send_ticket_to_admin(  # type: ignore[arg-type]
        bot, settings, ticket, user, access, "Нужна помощь"
    )
    assert bot.sent[0][0] == -100123456789
    assert bot.sent[0][2] is not None
