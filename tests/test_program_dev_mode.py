from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.mini_app import (
    complete_dev_program_day,
    dev_program_day,
    program_day,
    require_program_dev,
    reset_dev_program_day,
    save_dev_program_day_state,
)
from app.api.schemas import ProgramStepStateRequest
from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    DevProgramDayState,
    NicotineType,
    ProgramDayCompletion,
    ProgramDayState,
    ProgramProfile,
    QuitAttempt,
    SmokingProfile,
    User,
)
from app.services.program.engine import program_engine


def settings(*, enabled: bool, ids: str) -> Settings:
    return Settings(
        _env_file=None,
        dev_program_mode=enabled,
        dev_telegram_ids=ids,
    )


def test_program_dev_requires_both_switch_and_allowed_id() -> None:
    enabled = settings(enabled=True, ids="101, 202,invalid")
    assert enabled.is_program_dev(101)
    assert enabled.is_program_dev(202)
    assert enabled.is_program_dev(303) is False
    disabled = settings(enabled=False, ids="101,202")
    assert disabled.is_program_dev(101) is False
    assert disabled.is_program_dev(202) is False


async def make_context(tmp_path, telegram_id: int = 749408538):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'program-dev.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    session = sessions()
    user = User(
        telegram_id=telegram_id,
        telegram_first_name="Dev",
        program_started_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    session.add(user)
    await session.flush()
    profile = SmokingProfile(
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
    session.add(profile)
    session.add(
        ProgramProfile(
            user_id=user.id,
            quit_reasons=["health"],
            primary_quit_reason="health",
            user_triggers=["stress"],
            primary_triggers=["stress"],
            nicotine_beliefs=["stress_relief"],
            quit_concerns=[],
        )
    )
    await session.flush()
    return (user, profile, session), engine


def valid_value(step: dict[str, Any], overrides: dict[str, Any] | None = None) -> Any:
    if overrides and step["id"] in overrides:
        return overrides[step["id"]]
    step_type = step["type"]
    if step_type in {
        "single_select",
        "priority_select",
        "action_picker",
        "scenario_choice",
    }:
        return step["options"][0]["id"]
    if step_type == "multi_select":
        return [step["options"][0]["id"]]
    if step_type == "ordered_select":
        count = step["max_selections"] or 1
        return [item["id"] for item in step["options"][:count]]
    if step_type == "scale":
        return 1
    if step_type == "plan_builder":
        return {
            field["id"]: field["options"][0]["id"]
            for field in step["builder_fields"]
        }
    if step_type == "comparison":
        return {
            item["id"]: step["comparison"]["scale"][0]["id"]
            for item in step["comparison"]["items"]
        }
    return None


async def complete_preview(
    day_number: int,
    context: tuple[User, SmokingProfile, AsyncSession],
    overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, object], list[str]]:
    payload = await dev_program_day(day_number, context)
    visited: list[str] = []
    for _ in range(60):
        step = payload["step"]
        assert isinstance(step, dict)
        visited.append(str(step["id"]))
        if step["type"] == "completion":
            return await complete_dev_program_day(day_number, context), visited
        payload = await save_dev_program_day_state(
            day_number,
            ProgramStepStateRequest(
                step_id=step["id"], value=valid_value(step, overrides)
            ),
            context,
        )
    raise AssertionError("DEV preview did not reach completion")


@pytest.mark.asyncio
async def test_regular_user_cannot_use_dev_dependency_or_open_future_day(tmp_path) -> None:
    context, engine = await make_context(tmp_path, telegram_id=111)
    async with context[2]:
        with pytest.raises(HTTPException) as dev_error:
            await require_program_dev(context, settings(enabled=True, ids="749408538"))
        assert dev_error.value.status_code == 403
        with pytest.raises(HTTPException) as locked_error:
            await program_day(27, context)
        assert locked_error.value.status_code == 409
    await engine.dispose()


@pytest.mark.asyncio
async def test_dev_day_27_is_isolated_from_real_progress(tmp_path) -> None:
    context, engine = await make_context(tmp_path)
    user, _, session = context
    async with session:
        for day_number in (1, 2, 3):
            session.add(ProgramDayCompletion(user_id=user.id, day_number=day_number))
        attempt = QuitAttempt(
            user_id=user.id,
            started_at=datetime.now(timezone.utc) - timedelta(days=3),
        )
        session.add(attempt)
        await session.commit()
        started_at = user.program_started_at
        attempt_started_at = attempt.started_at

        payload, _ = await complete_preview(27, context)
        assert payload["completed"] is True
        assert program_engine.current_day(user) == 4
        assert user.program_started_at == started_at
        assert attempt.started_at == attempt_started_at
        assert await session.scalar(select(func.count(ProgramDayCompletion.id))) == 3
        assert await session.scalar(
            select(func.count(ProgramDayState.id)).where(
                ProgramDayState.day_number == 27
            )
        ) == 0
        assert await session.scalar(
            select(func.count(DevProgramDayState.id)).where(
                DevProgramDayState.day_number == 27,
                DevProgramDayState.completed.is_(True),
            )
        ) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_dev_day_27_reads_real_personalization_context(tmp_path) -> None:
    context, engine = await make_context(tmp_path)
    async with context[2]:
        payload = await dev_program_day(27, context)
        for _ in range(5):
            step = payload["step"]
            assert isinstance(step, dict)
            if step["type"] == "personalized_insight":
                insight = step["insight"]
                assert "Когда нервничаю" in insight["title"]
                break
            payload = await save_dev_program_day_state(
                27,
                ProgramStepStateRequest(
                    step_id=step["id"], value=valid_value(step)
                ),
                context,
            )
        else:
            raise AssertionError("Day 27 personalization was not shown")
    await engine.dispose()


@pytest.mark.asyncio
async def test_reset_only_clears_selected_dev_day(tmp_path) -> None:
    context, engine = await make_context(tmp_path)
    user, _, session = context
    async with session:
        production = ProgramDayState(
            user_id=user.id,
            day_number=17,
            current_step="completion",
            state_json={"production": "keep"},
            completed=True,
        )
        other_dev = DevProgramDayState(
            user_id=user.id,
            day_number=18,
            current_step="custom",
            state_json={"other": "keep"},
        )
        session.add_all([production, other_dev])
        await session.commit()
        await complete_preview(17, context)

        reset = await reset_dev_program_day(17, context)
        assert reset["step_index"] == 0
        assert reset["completed"] is False
        await session.refresh(production)
        await session.refresh(other_dev)
        assert production.state_json == {"production": "keep"}
        assert production.completed is True
        assert other_dev.state_json == {"other": "keep"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_day_22_can_repeat_different_branches_without_production_write(tmp_path) -> None:
    context, engine = await make_context(tmp_path)
    user, _, session = context
    async with session:
        _, risk_path = await complete_preview(22, context, {"one_time_first": "agree"})
        assert "one_time_risk_followup" in risk_path
        await reset_dev_program_day(22, context)
        _, coping_path = await complete_preview(22, context, {"one_time_first": "sos"})
        assert "one_time_coping_followup" in coping_path
        assert await session.scalar(
            select(func.count(ProgramDayState.id)).where(
                ProgramDayState.user_id == user.id,
                ProgramDayState.day_number == 22,
            )
        ) == 0
        assert await session.scalar(select(func.count(ProgramDayCompletion.id))) == 0
    await engine.dispose()
