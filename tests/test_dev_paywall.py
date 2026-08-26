from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import TelegramIdentity
from app.api.mini_app import (
    dashboard,
    get_access,
    profile,
    program,
    progress,
    require_active,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    NicotineType,
    SmokingProfile,
    Subscription,
    SubscriptionStatus,
    User,
)

DEV_ID = 749408538


def production_settings(*, enabled: bool = True, ids: str = str(DEV_ID)) -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        dev_auth_enabled=False,
        dev_program_mode=enabled,
        dev_telegram_ids=ids,
    )


async def make_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'dev-paywall.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)(), engine


async def make_user(session, telegram_id: int) -> tuple[User, SmokingProfile]:
    user = User(telegram_id=telegram_id, telegram_first_name="Tester")
    session.add(user)
    await session.flush()
    smoking_profile = SmokingProfile(
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
    )
    session.add(smoking_profile)
    await session.flush()
    return user, smoking_profile


@pytest.mark.asyncio
async def test_dev_user_gets_full_access_without_payment_or_subscription(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    settings = production_settings()
    identity = TelegramIdentity(DEV_ID, "Dev")
    async with session:
        user, _ = await make_user(session, DEV_ID)

        access = await get_access(identity, session, settings)
        context = await require_active(identity, session, settings)
        dashboard_payload = await dashboard(context)
        program_payload = await program(context, settings)
        progress_payload = await progress(context)
        profile_payload = await profile(context, settings)

        assert access["status"] == "active"
        assert access["plan"] == "developer"
        assert dashboard_payload["first_name"] == "Tester"
        assert program_payload["is_program_dev"] is True
        assert "achievements" in progress_payload
        assert profile_payload["access_status"] == "active"
        assert profile_payload["plan"] == "developer"
        assert await session.scalar(
            select(func.count(Subscription.id)).where(Subscription.user_id == user.id)
        ) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_ordinary_user_without_subscription_remains_blocked(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(111, "User")
    async with session:
        await make_user(session, 111)
        access = await get_access(identity, session, production_settings())
        assert access["status"] == "free"
        assert access["plan"] == "free"
        with pytest.raises(HTTPException) as exc_info:
            await require_active(identity, session, production_settings())
        assert exc_info.value.status_code == 402
    await engine.dispose()


@pytest.mark.asyncio
async def test_dev_program_mode_false_disables_paywall_bypass(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(DEV_ID, "Dev")
    async with session:
        await make_user(session, DEV_ID)
        access = await get_access(identity, session, production_settings(enabled=False))
        assert access["status"] == "free"
        with pytest.raises(HTTPException) as exc_info:
            await require_active(identity, session, production_settings(enabled=False))
        assert exc_info.value.status_code == 402
    await engine.dispose()


@pytest.mark.asyncio
async def test_foreign_id_does_not_receive_paywall_bypass(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(222, "Foreign")
    async with session:
        await make_user(session, 222)
        access = await get_access(identity, session, production_settings())
        assert access["status"] == "free"
        with pytest.raises(HTTPException) as exc_info:
            await require_active(identity, session, production_settings())
        assert exc_info.value.status_code == 402
    await engine.dispose()


@pytest.mark.asyncio
async def test_existing_premium_subscription_still_grants_access(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(333, "Premium")
    async with session:
        user, _ = await make_user(session, 333)
        session.add(
            Subscription(
                user_id=user.id,
                plan="premium",
                status=SubscriptionStatus.ACTIVE,
            )
        )
        await session.commit()

        access = await get_access(identity, session, production_settings())
        context = await require_active(identity, session, production_settings())
        profile_payload = await profile(context, production_settings())

        assert access["status"] == "active"
        assert access["plan"] == "premium"
        assert profile_payload["plan"] == "premium"
    await engine.dispose()


@pytest.mark.parametrize(
    ("telegram_id", "enabled", "expected_status"),
    [
        (101, True, "active"),
        (202, True, "active"),
        (303, True, "free"),
        (101, False, "free"),
        (202, False, "free"),
    ],
)
@pytest.mark.asyncio
async def test_multiple_verified_dev_ids_follow_single_list_and_flag(
    tmp_path, telegram_id: int, enabled: bool, expected_status: str
) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(telegram_id, "Verified")
    settings = production_settings(enabled=enabled, ids="101,202")
    async with session:
        await make_user(session, telegram_id)
        access = await get_access(identity, session, settings)
        assert access["status"] == expected_status
        assert access["plan"] == ("developer" if expected_status == "active" else "free")
        if expected_status == "active":
            context = await require_active(identity, session, settings)
            assert (await program(context, settings))["is_program_dev"] is True
            assert (await profile(context, settings))["plan"] == "developer"
        else:
            with pytest.raises(HTTPException) as exc_info:
                await require_active(identity, session, settings)
            assert exc_info.value.status_code == 402
    await engine.dispose()
