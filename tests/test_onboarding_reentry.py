from datetime import datetime, timezone
from decimal import Decimal

import pytest
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import onboarding
from app.bot.handlers import support as support_handlers
from app.bot.states.onboarding import OnboardingStates
from app.bot.texts.messages import (
    EDIT_PROFILE_CONFIRMATION,
    ONBOARDING_RESTART_CONFIRMATION,
    ONBOARDING_RESUME,
    PERSONAL_DATA_CONSENT,
    REPEAT_ONBOARDING_CONFIRMATION,
    RETURNING_USER,
    WELCOME,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    PaymentOrder,
    PaymentOrderStatus,
    ProgramDayCompletion,
    ProgramDayState,
    SmokingProfile,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.db.repositories import UserRepository
from app.services.expenses import ExpenseCalculator


class FakeApiBot:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def __call__(self, method: object, **_: object) -> object:
        self.calls.append(method)
        return True


class FakeState:
    def __init__(
        self,
        state: object | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        self.state = state
        self.data = data or {}

    async def clear(self) -> None:
        self.state = None
        self.data = {}

    async def get_state(self) -> str | None:
        return getattr(self.state, "state", self.state)

    async def set_state(self, state: object) -> None:
        self.state = state

    async def get_data(self) -> dict[str, object]:
        return self.data

    async def update_data(self, **data: object) -> None:
        self.data.update(data)


def settings() -> Settings:
    return Settings(
        _env_file=None,
        mini_app_url="https://airtgbot.ru/mini-app/",
        support_admin_chat_id="-100123456789",
    )


async def make_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'reentry.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


def telegram_user(telegram_id: int = 700001) -> TelegramUser:
    return TelegramUser(
        id=telegram_id,
        is_bot=False,
        first_name="Антон",
        username="anton",
    )


def user_message(bot: FakeApiBot, user: TelegramUser, text: str = "/start") -> Message:
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=user.id, type="private", first_name=user.first_name),
        from_user=user,
        text=text,
    ).as_(bot)  # type: ignore[arg-type]


def callback(
    bot: FakeApiBot,
    user: TelegramUser,
    data: str,
    *,
    message_id: int = 2,
) -> CallbackQuery:
    bot_user = TelegramUser(id=8618411820, is_bot=True, first_name="AIR")
    message = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=Chat(id=user.id, type="private", first_name=user.first_name),
        from_user=bot_user,
        text="AIR",
    ).as_(bot)  # type: ignore[arg-type]
    return CallbackQuery(
        id=f"callback-{message_id}",
        from_user=user,
        chat_instance="private-air",
        message=message,
        data=data,
    ).as_(bot)  # type: ignore[arg-type]


def sent_texts(bot: FakeApiBot) -> list[str]:
    return [
        call.text
        for call in bot.calls
        if isinstance(call, SendMessage) and isinstance(call.text, str)
    ]


def initial_answers(*, acquisition_source: str = "telegram") -> dict[str, object]:
    return {
        "gender": "male",
        "had_quit_attempts": True,
        "nicotine_type": "cigarettes",
        "cig_daily": 10,
        "cig_years": 5,
        "cig_pack_size": 20,
        "cig_pack_price": 250,
        "acquisition_source": acquisition_source,
    }


async def seed_consented_user(sessions, telegram_id: int = 700001) -> User:
    async with sessions() as session:
        user = User(
            telegram_id=telegram_id,
            telegram_first_name="Антон",
            username="anton",
            personal_data_consent_at=datetime.now(timezone.utc),
            personal_data_consent_version="1.0",
        )
        session.add(user)
        await session.commit()
        return user


async def complete_onboarding(sessions, telegram_id: int = 700001) -> None:
    async with sessions() as session:
        await UserRepository(session).save_onboarding(
            telegram_id=telegram_id,
            first_name="Антон",
            username="anton",
            answers=initial_answers(),
            result=ExpenseCalculator().calculate(initial_answers()),
        )


@pytest.mark.asyncio
async def test_new_consented_user_starts_regular_onboarding(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    await seed_consented_user(sessions)
    monkeypatch.setattr(onboarding, "session_factory", sessions)
    monkeypatch.setattr(onboarding, "get_settings", settings)
    bot = FakeApiBot()
    state = FakeState()

    await onboarding.start_onboarding(  # type: ignore[arg-type]
        user_message(bot, telegram_user()), state
    )

    assert state.state == OnboardingStates.answering
    assert state.data == {"current_question": "gender", "answers": {}}
    assert any(text.startswith("Привет, Антон!") for text in sent_texts(bot))
    await engine.dispose()


@pytest.mark.asyncio
async def test_partial_onboarding_offers_resume_and_continues_correct_question(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    await seed_consented_user(sessions)
    monkeypatch.setattr(onboarding, "session_factory", sessions)
    monkeypatch.setattr(onboarding, "get_settings", settings)
    bot = FakeApiBot()
    user = telegram_user()
    state = FakeState(
        OnboardingStates.answering,
        {"current_question": "had_quit_attempts", "answers": {"gender": "male"}},
    )

    await onboarding.start_onboarding(  # type: ignore[arg-type]
        user_message(bot, user), state
    )

    assert state.state == OnboardingStates.resume_choice
    assert state.data["answers"] == {"gender": "male"}
    assert ONBOARDING_RESUME in sent_texts(bot)

    await onboarding.continue_onboarding(  # type: ignore[arg-type]
        callback(bot, user, "onboarding:continue"), state
    )

    assert state.state == OnboardingStates.answering
    assert state.data["current_question"] == "had_quit_attempts"
    assert "Раньше уже были попытки отказаться от никотина?" in sent_texts(bot)
    await engine.dispose()


@pytest.mark.asyncio
async def test_restart_requires_confirmation_and_clears_only_fsm_answers(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    user_row = await seed_consented_user(sessions)
    monkeypatch.setattr(onboarding, "session_factory", sessions)
    monkeypatch.setattr(onboarding, "get_settings", settings)
    bot = FakeApiBot()
    user = telegram_user()
    state = FakeState(
        OnboardingStates.resume_choice,
        {"current_question": "nicotine_type", "answers": {"gender": "male"}},
    )

    await onboarding.request_onboarding_restart(  # type: ignore[arg-type]
        callback(bot, user, "onboarding:restart_request"), state
    )

    assert state.state == OnboardingStates.restart_confirmation
    assert state.data["answers"] == {"gender": "male"}
    assert ONBOARDING_RESTART_CONFIRMATION in {
        getattr(call, "text", None) for call in bot.calls
    }

    await onboarding.confirm_onboarding_restart(  # type: ignore[arg-type]
        callback(bot, user, "onboarding:restart_confirm", message_id=3), state
    )

    assert state.state == OnboardingStates.answering
    assert state.data == {"current_question": "gender", "answers": {}}
    async with sessions() as session:
        preserved = await session.get(User, user_row.id)
        assert preserved is not None
        assert preserved.personal_data_consent_version == "1.0"
        assert await session.scalar(select(func.count(SmokingProfile.id))) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_completed_onboarding_shows_returning_menu_and_requires_repeat_confirmation(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    await seed_consented_user(sessions)
    await complete_onboarding(sessions)
    monkeypatch.setattr(onboarding, "session_factory", sessions)
    monkeypatch.setattr(onboarding, "get_settings", settings)
    bot = FakeApiBot()
    user = telegram_user()
    state = FakeState()

    await onboarding.start_onboarding(  # type: ignore[arg-type]
        user_message(bot, user), state
    )

    assert state.state == OnboardingStates.returning
    assert RETURNING_USER in sent_texts(bot)
    assert not any(text.startswith("Привет, Антон!") for text in sent_texts(bot))
    returning_message = next(
        call
        for call in bot.calls
        if isinstance(call, SendMessage) and call.text == RETURNING_USER
    )
    assert returning_message.reply_markup is not None
    open_air = returning_message.reply_markup.inline_keyboard[0][0]
    assert open_air.web_app is not None
    assert open_air.web_app.url == "https://airtgbot.ru/mini-app/"

    before_request = len(sent_texts(bot))
    await onboarding.request_repeat_onboarding(  # type: ignore[arg-type]
        callback(bot, user, "onboarding:repeat_request"), state
    )
    assert state.state == OnboardingStates.repeat_confirmation
    assert REPEAT_ONBOARDING_CONFIRMATION in {
        getattr(call, "text", None) for call in bot.calls
    }
    assert sent_texts(bot)[before_request:] == []

    await onboarding.confirm_repeat_onboarding(  # type: ignore[arg-type]
        callback(bot, user, "onboarding:repeat_confirm", message_id=3), state
    )
    assert state.state == OnboardingStates.answering
    assert state.data == {"current_question": "gender", "answers": {}}
    assert WELCOME.format(first_name="Антон") in sent_texts(bot)
    await engine.dispose()


@pytest.mark.asyncio
async def test_returning_user_support_button_opens_support_for_callback_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bot = FakeApiBot()
    user = telegram_user()
    state = FakeState(OnboardingStates.returning)
    received: dict[str, object] = {}

    async def fake_open_support_flow(
        message: Message,
        received_state: FakeState,
        *,
        telegram_user: TelegramUser | None = None,
    ) -> None:
        received["message"] = message
        received["state"] = received_state
        received["telegram_user"] = telegram_user

    monkeypatch.setattr(
        support_handlers,
        "open_support_flow",
        fake_open_support_flow,
    )

    await onboarding.open_support_from_returning_user(  # type: ignore[arg-type]
        callback(bot, user, "onboarding:open_support"), state
    )

    assert received["state"] is state
    assert received["telegram_user"] == user


@pytest.mark.asyncio
async def test_edit_profile_deep_link_reuses_confirmed_repeat_flow(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    await seed_consented_user(sessions)
    await complete_onboarding(sessions)
    monkeypatch.setattr(onboarding, "session_factory", sessions)
    monkeypatch.setattr(onboarding, "get_settings", settings)
    bot = FakeApiBot()
    user = telegram_user()
    state = FakeState()

    await onboarding.edit_profile_deep_link(  # type: ignore[arg-type]
        user_message(bot, user, "/start edit_profile"), state
    )

    assert state.state == OnboardingStates.repeat_confirmation
    assert EDIT_PROFILE_CONFIRMATION in sent_texts(bot)
    assert not any(text.startswith("Привет, Антон!") for text in sent_texts(bot))

    await onboarding.confirm_repeat_onboarding(  # type: ignore[arg-type]
        callback(bot, user, "onboarding:repeat_confirm"), state
    )
    assert state.state == OnboardingStates.answering
    assert state.data == {"current_question": "gender", "answers": {}}
    await engine.dispose()


@pytest.mark.asyncio
async def test_edit_profile_deep_link_keeps_partial_flow(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    await seed_consented_user(sessions)
    monkeypatch.setattr(onboarding, "session_factory", sessions)
    monkeypatch.setattr(onboarding, "get_settings", settings)
    bot = FakeApiBot()
    state = FakeState(
        OnboardingStates.answering,
        {"current_question": "had_quit_attempts", "answers": {"gender": "male"}},
    )

    await onboarding.edit_profile_deep_link(  # type: ignore[arg-type]
        user_message(bot, telegram_user(), "/start edit_profile"), state
    )

    assert state.state == OnboardingStates.resume_choice
    assert state.data["current_question"] == "had_quit_attempts"
    assert ONBOARDING_RESUME in sent_texts(bot)
    await engine.dispose()


@pytest.mark.asyncio
async def test_edit_profile_deep_link_is_private_only() -> None:
    bot = FakeApiBot()
    user = telegram_user()
    message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=-100123456789, type="supergroup", title="AIR Support"),
        from_user=user,
        text="/start edit_profile",
    ).as_(bot)  # type: ignore[arg-type]
    state = FakeState()

    await onboarding.edit_profile_deep_link(message, state)  # type: ignore[arg-type]

    assert bot.calls == []
    assert state.state is None


@pytest.mark.asyncio
async def test_repeated_onboarding_preserves_program_subscription_and_payment_data(
    tmp_path,
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    user = await seed_consented_user(sessions)
    await complete_onboarding(sessions)
    program_started_at = datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc)
    async with sessions() as session:
        stored_user = await session.get(User, user.id)
        assert stored_user is not None
        stored_user.program_started_at = program_started_at
        stored_user.receipt_email = "buyer@example.com"
        session.add_all(
            [
                Subscription(
                    user_id=user.id,
                    plan="air_30_days",
                    status=SubscriptionStatus.ACTIVE,
                    starts_at=program_started_at,
                ),
                PaymentOrder(
                    user_id=user.id,
                    plan_id="air_30_days",
                    amount=Decimal("990"),
                    currency="RUB",
                    status=PaymentOrderStatus.SUCCEEDED,
                    yookassa_payment_id="payment-preserved",
                    idempotency_key="11111111-1111-1111-1111-111111111111",
                    receipt_email="buyer@example.com",
                    paid_at=program_started_at,
                ),
                ProgramDayState(
                    user_id=user.id,
                    day_number=4,
                    current_step="reflection",
                    state_json={"answer": "Сохранить"},
                    completed=False,
                ),
                ProgramDayCompletion(user_id=user.id, day_number=3),
            ]
        )
        await session.commit()

    updated_answers = initial_answers(acquisition_source="friends")
    updated_answers["cig_daily"] = 5
    async with sessions() as session:
        await UserRepository(session).save_onboarding(
            telegram_id=user.telegram_id,
            first_name="Антон",
            username="anton",
            answers=updated_answers,
            result=ExpenseCalculator().calculate(updated_answers),
        )

    async with sessions() as session:
        stored_user = await session.get(User, user.id)
        program_state = await session.scalar(select(ProgramDayState))
        assert stored_user is not None
        assert stored_user.program_started_at is not None
        assert stored_user.program_started_at.replace(tzinfo=timezone.utc) == program_started_at
        assert stored_user.receipt_email == "buyer@example.com"
        assert stored_user.personal_data_consent_version == "1.0"
        assert stored_user.acquisition_source == "friends"
        assert await session.scalar(select(func.count(Subscription.id))) == 1
        assert await session.scalar(select(func.count(PaymentOrder.id))) == 1
        assert await session.scalar(select(func.count(ProgramDayCompletion.id))) == 1
        assert program_state is not None
        assert program_state.day_number == 4
        assert program_state.current_step == "reflection"
        assert program_state.state_json == {"answer": "Сохранить"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_without_consent_still_gets_existing_consent_flow(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions, engine = await make_sessions(tmp_path)
    monkeypatch.setattr(onboarding, "session_factory", sessions)
    monkeypatch.setattr(onboarding, "get_settings", settings)
    bot = FakeApiBot()

    await onboarding.start_onboarding(  # type: ignore[arg-type]
        user_message(bot, telegram_user()), FakeState()
    )

    assert PERSONAL_DATA_CONSENT in sent_texts(bot)
    await engine.dispose()
