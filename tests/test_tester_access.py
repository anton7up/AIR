from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import TelegramIdentity, get_telegram_identity
from app.api.mini_app import (
    get_access,
    profile,
    program,
    refresh_access,
    require_active,
    require_program_dev,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    NicotineType,
    ProgramDayState,
    SmokingProfile,
    Subscription,
    User,
    UserResponse,
    UserResponseType,
)

TESTER_ID = 111111111
DEV_ID = 749408538


def settings(*, tester_enabled: bool = True, tester_ids: str = str(TESTER_ID)) -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        dev_auth_enabled=False,
        dev_program_mode=True,
        dev_telegram_ids=str(DEV_ID),
        tester_access_enabled=tester_enabled,
        tester_telegram_ids=tester_ids,
    )


async def make_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tester-access.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)(), engine


async def make_user(session, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id, telegram_first_name="Tester")
    session.add(user)
    await session.flush()
    session.add(SmokingProfile(
        user_id=user.id,
        nicotine_type=NicotineType.CIGARETTES,
        years_of_use=Decimal("3"),
        daily_units=Decimal("10"),
        consumption_parameters={},
        cost_parameters={},
        monthly_expense=Decimal("3000"),
        yearly_expense=Decimal("36000"),
        lifetime_expense=Decimal("108000"),
        projected_five_year_expense=Decimal("180000"),
    ))
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_allowlisted_tester_claims_full_access_without_subscription_or_dev(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(TESTER_ID, "Tester")
    current_settings = settings()
    async with session:
        user = await make_user(session, TESTER_ID)

        initial = await get_access(identity, session, current_settings)
        claimed = await refresh_access(identity, session, current_settings)
        context = await require_active(identity, session, current_settings)
        program_payload = await program(context, current_settings)
        profile_payload = await profile(context, current_settings)

        assert initial["status"] == "free"
        assert claimed["status"] == "active"
        assert claimed["plan"] == "tester"
        assert program_payload["is_program_dev"] is False
        days = program_payload["days"]
        assert isinstance(days, list)
        assert all(
            isinstance(day, dict) and day.get("dev_preview_available") is False
            for day in days
        )
        assert profile_payload["plan"] == "tester"
        assert await session.scalar(
            select(func.count(Subscription.id)).where(Subscription.user_id == user.id)
        ) == 0
        with pytest.raises(HTTPException) as exc_info:
            await require_program_dev(context, current_settings)
        assert exc_info.value.status_code == 403
    await engine.dispose()


@pytest.mark.parametrize(
    ("telegram_id", "enabled"),
    [(222222222, True), (TESTER_ID, False)],
)
@pytest.mark.asyncio
async def test_foreign_or_disabled_tester_stays_behind_paywall(
    tmp_path, telegram_id: int, enabled: bool
) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(telegram_id, "User")
    current_settings = settings(tester_enabled=enabled)
    async with session:
        await make_user(session, telegram_id)
        claimed = await refresh_access(identity, session, current_settings)
        assert claimed["status"] == "free"
        assert claimed["plan"] == "free"
        with pytest.raises(HTTPException) as exc_info:
            await require_active(identity, session, current_settings)
        assert exc_info.value.status_code == 402
    await engine.dispose()


@pytest.mark.asyncio
async def test_production_dev_header_cannot_spoof_allowlisted_tester() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_telegram_identity(
            init_data=None,
            dev_telegram_id=TESTER_ID,
            settings=settings(),
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_removing_tester_access_preserves_product_data(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(TESTER_ID, "Tester")
    async with session:
        user = await make_user(session, TESTER_ID)
        session.add(ProgramDayState(
            user_id=user.id,
            day_number=1,
            current_step="reason",
            state_json={"reason": "family"},
        ))
        session.add(UserResponse(
            user_id=user.id,
            response_type=UserResponseType.REASON,
            value="Ради семьи",
            normalized_value="ради семьи",
            source="program",
            source_ref="day:1:reason",
        ))
        await session.commit()

        assert (await refresh_access(identity, session, settings()))["status"] == "active"
        disabled = settings(tester_enabled=False)
        assert (await refresh_access(identity, session, disabled))["status"] == "free"
        assert await session.scalar(
            select(func.count(ProgramDayState.id)).where(ProgramDayState.user_id == user.id)
        ) == 1
        assert await session.scalar(
            select(func.count(UserResponse.id)).where(UserResponse.user_id == user.id)
        ) == 1
    await engine.dispose()
