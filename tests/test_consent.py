from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import TelegramIdentity
from app.api.mini_app import (
    accept_consent,
    get_consent_status,
    require_active_consent,
    require_program_dev,
    router,
)
from app.db.base import Base
from app.db.models import NicotineType, SmokingProfile, User
from app.db.repositories import UserRepository
from app.services.consent import CURRENT_PERSONAL_DATA_CONSENT_VERSION
from app.services.expenses import ExpenseCalculator


async def make_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'consent.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)(), engine


def answers() -> dict[str, object]:
    return {
        "gender": "male",
        "had_quit_attempts": False,
        "nicotine_type": "cigarettes",
        "cig_daily": 10,
        "cig_years": 3,
        "cig_pack_size": 20,
        "cig_pack_price": 200,
        "acquisition_source": "telegram",
    }


@pytest.mark.asyncio
async def test_new_and_existing_user_need_consent_then_accept_is_persistent(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(900001, "Новый", "new_user")
    async with session:
        initial = await get_consent_status(identity, session)
        assert initial["accepted"] is False
        assert await session.scalar(select(func.count(User.id))) == 0

        accepted = await accept_consent(identity, session)
        assert accepted["accepted"] is True
        assert accepted["consent_version"] == CURRENT_PERSONAL_DATA_CONSENT_VERSION
        assert isinstance(accepted["consent_at"], datetime)

        first_timestamp = accepted["consent_at"]
        repeated = await accept_consent(identity, session)
        assert repeated["consent_at"] == first_timestamp
        assert (await get_consent_status(identity, session))["accepted"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_existing_data_is_preserved_when_user_accepts(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    identity = TelegramIdentity(900002, "Существующий", "existing")
    async with session:
        user = User(
            telegram_id=identity.telegram_id,
            telegram_first_name=identity.first_name,
            username=identity.username,
            motivation="Сохранённая мотивация",
        )
        session.add(user)
        await session.flush()
        session.add(
            SmokingProfile(
                user_id=user.id,
                nicotine_type=NicotineType.CIGARETTES,
                years_of_use=Decimal("4"),
                daily_units=Decimal("10"),
                consumption_parameters={},
                cost_parameters={},
                monthly_expense=Decimal("3000"),
                yearly_expense=Decimal("36000"),
                lifetime_expense=Decimal("144000"),
                projected_five_year_expense=Decimal("180000"),
            )
        )
        await session.commit()

        assert (await get_consent_status(identity, session))["accepted"] is False
        await accept_consent(identity, session)
        preserved = await session.scalar(select(User).where(User.id == user.id))
        assert preserved is not None
        assert preserved.motivation == "Сохранённая мотивация"
        assert preserved.personal_data_consent_version == "1.0"
        assert await session.scalar(
            select(func.count(SmokingProfile.id)).where(SmokingProfile.user_id == user.id)
        ) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_onboarding_cannot_store_sensitive_data_without_consent(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        session.add(User(telegram_id=900003, telegram_first_name="Без согласия"))
        await session.commit()
        values = answers()
        with pytest.raises(HTTPException) as exc_info:
            await UserRepository(session).save_onboarding(
                900003,
                "Без согласия",
                None,
                values,
                ExpenseCalculator().calculate(values),
            )
        assert exc_info.value.status_code == 428
        assert await session.scalar(select(func.count(SmokingProfile.id))) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_tester_dev_or_admin_status_does_not_replace_consent(tmp_path) -> None:
    session, engine = await make_session(tmp_path)
    async with session:
        user = User(telegram_id=900004, telegram_first_name="Привилегированный")
        session.add(user)
        await session.flush()
        profile = SmokingProfile(
            user_id=user.id,
            nicotine_type=NicotineType.CIGARETTES,
            years_of_use=Decimal("1"),
            daily_units=Decimal("5"),
            consumption_parameters={},
            cost_parameters={},
            monthly_expense=Decimal("1000"),
            yearly_expense=Decimal("12000"),
            lifetime_expense=Decimal("12000"),
            projected_five_year_expense=Decimal("60000"),
        )
        session.add(profile)
        await session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await require_active_consent((user, profile, session))
        assert exc_info.value.status_code == 428

        user.personal_data_consent_at = datetime.now(timezone.utc)
        user.personal_data_consent_version = "1.0"
        assert await require_active_consent((user, profile, session)) == (
            user,
            profile,
            session,
        )
    await engine.dispose()


def test_all_program_and_sos_routes_have_backend_consent_guard() -> None:
    sensitive_prefixes = (
        "/api/v1/mini-app/dashboard",
        "/api/v1/mini-app/program",
        "/api/v1/mini-app/dev/program",
        "/api/v1/mini-app/sos",
        "/api/v1/mini-app/support-context",
        "/api/v1/mini-app/responses",
        "/api/v1/mini-app/motivation",
        "/api/v1/mini-app/nicotine-desire",
        "/api/v1/mini-app/lapse",
        "/api/v1/mini-app/quit-attempt",
        "/api/v1/mini-app/progress",
        "/api/v1/mini-app/profile",
    )
    guarded_paths: set[str] = set()
    for route_item in router.routes:
        path = getattr(route_item, "path", "")
        if not path.startswith(sensitive_prefixes):
            continue
        calls = {dependency.call for dependency in route_item.dependant.dependencies}
        assert calls & {require_active_consent, require_program_dev}, path
        guarded_paths.add(path)
    assert "/api/v1/mini-app/program/start" in guarded_paths
    assert "/api/v1/mini-app/sos/start" in guarded_paths
    assert "/api/v1/mini-app/responses" in guarded_paths
