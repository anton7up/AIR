from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import onboarding
from app.bot.texts.messages import PERSONAL_DATA_CONSENT
from app.db.base import Base
from app.db.models import User


class FakeState:
    def __init__(self) -> None:
        self.cleared = False
        self.state: object | None = None
        self.data: dict[str, object] = {}

    async def clear(self) -> None:
        self.cleared = True
        self.state = None
        self.data = {}

    async def set_state(self, state: object) -> None:
        self.state = state

    async def update_data(self, **data: object) -> None:
        self.data.update(data)


class FakeMessage:
    def __init__(self, chat_type: str) -> None:
        self.chat = SimpleNamespace(id=2001, type=chat_type)
        self.from_user = SimpleNamespace(
            id=2001,
            first_name="Антон",
            username="anton",
        )
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup: object | None = None) -> None:
        self.answers.append((text, reply_markup))


async def make_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'chat-scope.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


@pytest.mark.asyncio
async def test_start_in_private_chat_keeps_existing_consent_flow(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    monkeypatch.setattr(onboarding, "session_factory", sessions)
    monkeypatch.setattr(
        onboarding,
        "get_settings",
        lambda: SimpleNamespace(mini_app_url="https://example.com/mini-app/"),
    )
    message = FakeMessage("private")
    state = FakeState()

    await onboarding.start_onboarding(message, state)  # type: ignore[arg-type]

    assert state.cleared is True
    assert message.answers[0][0] == PERSONAL_DATA_CONSENT
    async with sessions() as session:
        assert await session.scalar(select(func.count(User.id))) == 1
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
async def test_start_in_group_does_not_start_onboarding(
    tmp_path, monkeypatch: pytest.MonkeyPatch, chat_type: str
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    monkeypatch.setattr(onboarding, "session_factory", sessions)
    message = FakeMessage(chat_type)
    state = FakeState()

    await onboarding.start_onboarding(message, state)  # type: ignore[arg-type]

    assert state.cleared is False
    assert message.answers == []
    async with sessions() as session:
        assert await session.scalar(select(func.count(User.id))) == 0
    await engine.dispose()
